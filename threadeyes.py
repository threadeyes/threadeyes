#!/usr/bin/env python3
"""ThreadEyes: how much each Claude Code thread spends, what kind of work it does, and which model fits it.

It reads, on this computer only, the conversation logs Claude Code already keeps
(by default ~/.claude/projects/**/*.jsonl) and writes two files: a Markdown report and an HTML panel.
It makes no network request and sends nothing anywhere. See PRIVACY.md.

What sets it apart: it groups by the NAME you gave the thread and treats its hand-offs as the same thread.

Usage:
    python threadeyes.py                       # last 8 weeks, language from your system
    python threadeyes.py --weeks 12 --lang es
    python threadeyes.py --config threadeyes.json --out my-report
    python threadeyes.py --logs path/to/projects      # e.g. the demo data in examples/

The money shown is a weighted spend at API prices. With a subscription it is NOT what you pay:
it only lets you compare how heavy each thread is.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

sys.dont_write_bytecode = True  # leave no __pycache__ folder behind: the only files written are the two reports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n  # noqa: E402
import panel  # noqa: E402

__version__ = '0.1.0'

# --------------------------------------------------------------------------- prices
# API prices, USD per million tokens. A static table dated 2026-11-03: CHECK IT against Anthropic's
# pricing page and override it in the config file ("prices") if it is out of date.
# Cache writes are counted at 1.25 x the input price. They only serve to weigh models against each other.
PRICES = {
    'opus':   {'in': 4.0, 'out': 20.0, 'cr': 0.20},
    'sonnet': {'in': 2.0, 'out': 10.0, 'cr': 0.10},
    'haiku':  {'in': 0.10, 'out': 0.50, 'cr': 0.01},
    'fable':  {'in': 8.0, 'out': 40.0, 'cr': 0.20},
}
# Exact price when a version differs from its family. The first match wins, so the most specific goes first.
EXACT_PRICES = {
    'opus-5-5': {'in': 4.0, 'out': 20.0, 'cr': 0.20},
    'opus-5':   {'in': 5.0, 'out': 25.0, 'cr': 0.50},
    'opus-4':   {'in': 5.0, 'out': 25.0, 'cr': 0.50},
    'fable-5-2': {'in': 8.0, 'out': 40.0, 'cr': 0.20},
    'fable-5':  {'in': 10.0, 'out': 50.0, 'cr': 1.00},
    'sonnet-5': {'in': 2.0, 'out': 10.0, 'cr': 0.20},
    'sonnet-4': {'in': 3.0, 'out': 15.0, 'cr': 0.30},
    'haiku-5-5': {'in': 0.10, 'out': 0.50, 'cr': 0.01},
    'haiku-4':  {'in': 1.0, 'out': 5.0, 'cr': 0.10},
}
FAMILIES = ('fable', 'opus', 'sonnet', 'haiku')
USAGE_FIELDS = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')

# --------------------------------------------------------------------------- what a tool call means
CLASSES = ('build', 'test', 'read', 'coordinate')
EDIT_TOOLS = {'Write', 'Edit', 'NotebookEdit', 'MultiEdit'}
READ_TOOLS = {'Read', 'Grep', 'Glob', 'WebFetch', 'WebSearch'}
COORD_TOOLS = {'SendMessage', 'Agent', 'Task', 'TodoWrite', 'Skill', 'ToolSearch', 'AskUserQuestion'}
# Shell commands that run or test things, as opposed to just looking at files.
TEST_COMMANDS = {'node', 'npm', 'npx', 'git', 'python', 'python3', 'py', 'pytest', 'curl', 'timeout',
                 'gh', 'pnpm', 'yarn', 'deno', 'start-process', 'invoke-webrequest',
                 'cargo', 'go', 'make', 'dotnet', 'mvn', 'gradle', 'docker', 'pip', 'pip3', 'uv', 'bun'}
BARS = ' ▁▂▃▄▅▆▇█'

# --------------------------------------------------------------------------- configuration
DEFAULT_CONFIG = {
    'language': 'auto',          # auto | en | es
    'weeks': 8,
    # Section of a thread = the last folder of its working directory. To name or merge sections:
    # {"my-repo": "Billing"} means "any working folder containing my-repo is the section Billing".
    'projects': {},
    # Old thread name -> current name, for threads you renamed.
    'aliases': {},
    # Several spellings that are one thread: [{"name": "Docs", "contains_all": ["docs", "site"]}]
    'merge_groups': [],
    # Words (prefixes, accent and case insensitive) that mark a thread as judgment work, which stays on the
    # most capable model. Replaces the defaults when given.
    'judgment_keywords': ['architect', 'arquitect', 'design', 'diseñ', 'strateg', 'estrateg', 'review',
                          'revis', 'decid', 'decision', 'audit'],
    # Thread names starting with these are scheduled tasks (suggested for the cheaper model).
    'scheduled_prefixes': [],
    # Text at the end of a title that marks a hand-off copy of the same thread. Two shapes:
    #   after a separator ( · - – — : ( [ ) the word and anything after it: "Docs · relevo 12/11", "Docs (cont. 2)"
    #   after a space, the word and only numbers/dates: "Docs relevo 4"
    'relay_pattern': r'\s*[·\-–—:(\[]\s*(?:relevad[oa]|relevo|hand-?off|handover|continued|cont\.?)(?![^\W\d_]).*$'
                     r'|\s+(?:relevad[oa]|relevo|hand-?off|handover|continued|cont\.?)(?:\s+[\d/.\-]+)*\s*$',
    # Price overrides, same shape as PRICES, e.g. {"opus": {"in": 5, "out": 25, "cr": 0.5}}
    'prices': {},
}


class ConfigError(Exception):
    pass


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    if path:
        try:
            with open(path, encoding='utf-8-sig') as f:
                user = json.load(f)
        except (OSError, ValueError) as e:
            raise ConfigError(f'{path}: {e}')
        if not isinstance(user, dict):
            raise ConfigError(f'{path}: the file must contain a JSON object')
        unknown = set(user) - set(DEFAULT_CONFIG)
        if unknown:
            print(f'Warning: unknown config keys ignored: {", ".join(sorted(unknown))}', file=sys.stderr)
        cfg.update({k: v for k, v in user.items() if k in DEFAULT_CONFIG})
    return cfg


def find_config(explicit):
    if explicit:
        return explicit
    for cand in (os.path.join(os.getcwd(), 'threadeyes.json'), os.path.expanduser('~/.threadeyes.json')):
        if os.path.isfile(cand):
            return cand
    return None


# --------------------------------------------------------------------------- helpers
def fold(s):
    """Upper case without accents, for comparing names."""
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).upper()


def family(model):
    m = (model or '').lower()
    for f in PRICES:
        if f in m:
            return f
    return None


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def cost(fam, model, usage, cfg):
    p = dict(PRICES[fam])
    m = (model or '').lower()
    for key, price in EXACT_PRICES.items():
        if key in m:
            p = dict(price)
            break
    p.update((cfg.get('prices') or {}).get(fam, {}))
    return (num(usage.get('input_tokens')) * p['in']
            + num(usage.get('cache_creation_input_tokens')) * p['in'] * 1.25
            + num(usage.get('cache_read_input_tokens')) * p['cr']
            + num(usage.get('output_tokens')) * p['out']) / 1e6


def tool_class(block):
    n = block.get('name', '')
    if n in EDIT_TOOLS:
        return 'build'
    if n in READ_TOOLS:
        return 'read'
    if n in COORD_TOOLS or 'send_message' in n or 'update_plan' in n or 'wrap_up' in n or 'mark_chapter' in n:
        return 'coordinate'
    if 'Browser' in n or 'chrome' in n or 'computer' in n or 'preview' in n:
        return 'test'
    if n in ('Bash', 'PowerShell'):
        cmd = (block.get('input') or {}).get('command') or ''
        for part in re.split(r'&&|;|\|', cmd):
            part = part.strip()
            if not part:
                continue
            w = part.split()[0].lower().strip('"\'')
            if w in ('cd', 'set-location', 'export', 'echo', 'sleep', 'date'):
                continue
            if '=' in w and not w.startswith('-'):
                continue
            return 'test' if w in TEST_COMMANDS else 'read'
        return 'read'
    return 'coordinate'


def section_of(cwd, cfg, tx):
    c = (cwd or '')
    low = c.lower()
    for key, name in (cfg.get('projects') or {}).items():
        if key.lower() in low:
            return name
    parts = [p for p in re.split(r'[\\/]', c) if p]
    return parts[-1] if parts else tx['other']


def lineage(title, cfg):
    """Thread name without the hand-off suffix, after aliases and merge groups."""
    t = re.sub(cfg['relay_pattern'], '', title.strip(), flags=re.I).strip() or title.strip()
    aliases = {fold(k): v for k, v in (cfg.get('aliases') or {}).items()}
    if fold(t) in aliases:
        return aliases[fold(t)]
    words = re.sub(r'[^A-Z0-9 ]', ' ', fold(t)).split()
    for g in cfg.get('merge_groups') or []:
        if all(fold(w) in words for w in g.get('contains_all', [])):
            return g['name']
    return t


def is_scheduled(name, cfg):
    low = name.lower()
    return any(low.startswith(p.lower()) for p in cfg.get('scheduled_prefixes') or [])


def is_judgment(name, cfg):
    words = re.sub(r'[^A-Z0-9 ]', ' ', fold(name)).split()
    keys = [fold(k) for k in cfg.get('judgment_keywords') or []]
    return any(w.startswith(k) for w in words for k in keys if k)


def cell(s):
    """Text safe inside a Markdown table cell or list item."""
    return str(s).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')


def sparkline(vals):
    top = max(vals) or 1
    return ''.join(BARS[max(1, min(8, round(8 * v / top)))] if v > 0 else '·' for v in vals)


def bar(v, top, width=20):
    return '█' * max(1, round(width * v / top)) if v > 0 else ''


def monday(d):
    return d - dt.timedelta(days=d.weekday())


# --------------------------------------------------------------------------- reading the logs
def read_sessions(base, since, cfg, tx):
    """One entry per session: title, working folders and one note per assistant turn."""
    sessions = {}
    # Claude Code writes ONE line per content block (text, tool call...) of the same assistant message,
    # each carrying the message's full token usage. Counting every line would multiply that message's cost
    # by its number of blocks, so the cost of a message (identified by message.id) is counted once.
    # Tool calls are still counted per line, because each line holds one call. Resumed sessions copy
    # earlier messages into the new file; the first copy found (files in sorted order) keeps the cost.
    seen = {}
    paths = sorted(glob.glob(os.path.join(glob.escape(base), '**', '*.jsonl'), recursive=True))
    for path in paths:
        parts = os.path.relpath(path, base).split(os.sep)
        key = parts[1].replace('.jsonl', '') if len(parts) > 1 else parts[0]
        s = sessions.setdefault(key, {'title': None, 'cwds': defaultdict(int), 'notes': []})
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(d, dict):
                        continue
                    if isinstance(d.get('customTitle'), str) and d['customTitle'].strip():
                        s['title'] = d['customTitle']
                    if isinstance(d.get('cwd'), str) and d['cwd']:
                        s['cwds'][section_of(d['cwd'], cfg, tx)] += 1
                    msg = d.get('message')
                    if not isinstance(msg, dict) or msg.get('role') != 'assistant':
                        continue
                    try:
                        t = dt.datetime.fromisoformat(d['timestamp'].replace('Z', '+00:00')).astimezone()
                    except Exception:
                        continue
                    if t.date() < since:
                        continue
                    model = msg.get('model')
                    fam = family(model if isinstance(model, str) else None)
                    usage = msg.get('usage') if isinstance(msg.get('usage'), dict) else {}
                    blocks = msg.get('content') if isinstance(msg.get('content'), list) else []
                    tools = [tool_class(b) for b in blocks if isinstance(b, dict) and b.get('type') == 'tool_use']
                    note = [t.date(), fam, 0.0, tools]
                    s['notes'].append(note)
                    if not (fam and usage):
                        continue
                    mid = msg.get('id')
                    if not isinstance(mid, str) or not mid:
                        note[2] = cost(fam, model, usage, cfg)  # no id: cannot tell repeats apart
                    elif mid in seen:
                        u = seen[mid][2]  # the same message again: keep the largest figure of each field
                        for k in USAGE_FIELDS:
                            u[k] = max(num(u.get(k)), num(usage.get(k)))
                    else:
                        seen[mid] = (note, model, {k: num(usage.get(k)) for k in USAGE_FIELDS})
        except OSError:
            continue
    for note, model, usage in seen.values():
        note[2] = cost(note[1], model, usage, cfg)
    return sessions


def build_threads(sessions, weeks, since, cfg, tx):
    """Join sessions into threads: the same name, hand-offs and renames count as one."""
    threads = {}
    per_day = defaultdict(float)
    for s in sessions.values():
        if not s['notes']:
            continue
        home = max(s['cwds'], key=s['cwds'].get) if s['cwds'] else tx['other']
        name = lineage(s['title'], cfg) if s['title'] else tx['unnamed'].format(where=home)
        key = (' '.join(name.casefold().split()), home)
        h = threads.setdefault(key, {'name': name, 'home': home, 'wk': [0.0] * weeks, 'fam': defaultdict(float),
                                     'tools': defaultdict(int), 'turns': 0, 'sessions': 0,
                                     'last': None, 'rel': [], 'now': None, 'now_day': None})
        h['sessions'] += 1
        sf, st = defaultdict(float), defaultdict(int)
        sc = 0.0
        for day, fam, c, tools in s['notes']:
            sc += c
            if fam:
                sf[fam] += c
            for n_ in tools:
                st[n_] += 1
        if sf:
            nt = sum(st.values()) or 1
            h['rel'].append({'date': min(a[0] for a in s['notes']), 'fam': max(sf, key=sf.get), 'cost': sc,
                             'rep': {k: st.get(k, 0) / nt for k in CLASSES}})
            last = max(s['notes'], key=lambda a: a[0])
            last_fam = next((a[1] for a in reversed(s['notes']) if a[1]), None)
            if last_fam and (h['now_day'] is None or last[0] >= h['now_day']):
                h['now'], h['now_day'] = last_fam, last[0]
        for day, fam, c, tools in s['notes']:
            k = (monday(day) - since).days // 7
            if 0 <= k < weeks:
                h['wk'][k] += c
            per_day[day] += c
            if fam:
                h['fam'][fam] += c
                h['turns'] += 1
            for n_ in tools:
                h['tools'][n_] += 1
            h['last'] = max(h['last'] or day, day)
    return threads, per_day


def analyse(threads, cfg):
    """Type of work, suggested model, possible saving and diagnosis for each thread."""
    rows = []
    for h in threads.values():
        total = sum(h['wk'])
        if total <= 0:
            continue
        name = h['name']
        tools = h['tools']
        n = sum(tools.values())
        share = {k: tools.get(k, 0) / (n or 1) for k in CLASSES}
        if is_scheduled(name, cfg):
            kind, reco = 'scheduled', 'sonnet'
        else:
            if n == 0 or n / max(h['turns'], 1) < 0.3:
                kind = 'decide'
            elif share['build'] >= 0.08 and share['build'] + share['test'] >= 0.3:
                kind = 'build'
            elif share['coordinate'] >= 0.4:
                kind = 'coordinate'
            elif share['read'] >= 0.6:
                kind = 'research'
            else:
                kind = 'mixed'
            reco = 'opus' if (is_judgment(name, cfg) or kind == 'decide') else 'sonnet'
        used = max(h['fam'], key=h['fam'].get)
        tf = sum(h['fam'].values()) or 1
        models = {f: h['fam'].get(f, 0) / tf for f in FAMILIES}
        two = sum(1 for x in models.values() if x >= 0.2) >= 2
        # Split, or just switch model? Compare the hand-offs of each model: if they do different work, split.
        groups = defaultdict(lambda: {'c': 0.0, 'rep': defaultdict(float)})
        for rl in h['rel']:
            g = groups[rl['fam']]
            g['c'] += rl['cost']
            for k_ in CLASSES:
                g['rep'][k_] += rl['rep'][k_] * rl['cost']
        strong = sorted([(g['c'], f) for f, g in groups.items() if g['c'] / tf >= 0.2], reverse=True)
        distance = 0.0
        if len(strong) >= 2:
            a_, b_ = groups[strong[0][1]], groups[strong[1][1]]
            distance = max(abs(a_['rep'][k_] / a_['c'] - b_['rep'][k_] / b_['c']) for k_ in CLASSES)
        # The saving is measured from the model the thread uses NOW, not from its history.
        now = h['now'] or used
        saving, costly = 0.0, []
        if PRICES[reco]['out'] < PRICES[now]['out']:
            saving = total * (1 - PRICES[reco]['out'] / PRICES[now]['out'])
            costly.append(now)
        if len(strong) >= 2 and len(h['rel']) >= 3 and distance >= 0.15 and not is_scheduled(name, cfg):
            diag = 'split'
        elif saving > 0 or (len(strong) >= 2 and now != reco):
            diag = 'switch'
        else:
            diag = 'ok'
        rows.append({'diag': diag, 'now': now, 'rel': h['rel'], 'name': name, 'home': h['home'], 'total': total,
                     'wk': h['wk'], 'kind': kind, 'costly': '/'.join(sorted(costly)), 'reco': reco, 'saving': saving,
                     'relays': h['sessions'] - 1, 'models': models, 'two': two, 'last': h['last'],
                     'share': share})
    rows.sort(key=lambda r: -r['total'])
    return rows


# --------------------------------------------------------------------------- output
def write_report(path, rows, weeks, since_list, today, per_day, tx):
    T = sum(r['total'] for r in rows) or 1
    saving = sum(r['saving'] for r in rows)
    wk_tot = [sum(r['wk'][k] for r in rows) for k in range(weeks)]
    sections = defaultdict(lambda: [0.0] * weeks)
    for r in rows:
        for k in range(weeks):
            sections[r['home']][k] += r['wk'][k]
    top = sorted([r for r in rows if r['saving'] > 0], key=lambda r: -r['saving'])[:3]
    labels = [d.strftime('%d/%m') for d in since_list]
    pct = lambda v: f'{100 * v / T:.1f}%'

    L = [f'# ' + tx['md_title'].format(weeks=weeks, start=f'{since_list[0]:%d/%m}', end=f'{today:%d/%m/%Y}'), '',
         '> **' + tx['md_summary'].format(pct=f'{100 * saving / T:.0f}').replace('**', '') + '**']
    for r in top:
        L.append('> - ' + tx['md_summary_item'].format(name=cell(r['name']), where=cell(r['home']), now=r['costly'], reco=r['reco'],
                                                       pct=f"{100 * r['saving'] / T:.0f}"))
    if not top:
        L.append('> - ' + tx['md_none_change'])
    recos = sorted([r for r in rows if r['saving'] / T >= 0.001 or r['diag'] != 'ok'], key=lambda r: -r['saving'])
    L += ['', f"## {tx['md_recos_title']}", '']
    for r in recos:
        if r['saving'] / T >= 0.001:
            L.append('- ' + tx['md_reco_line'].format(name=cell(r['name']), now=r['costly'], reco=r['reco'], kind=tx['type_' + r['kind']].lower(),
                                                      pct=f"{100 * r['saving'] / T:.1f}", diag=tx['diag_' + r['diag']].lower()))
        else:
            L.append('- ' + tx['md_reco_nosave'].format(name=cell(r['name']), kind=tx['type_' + r['kind']].lower(),
                                                        diag=tx['diag_' + r['diag']].lower()))
    if not recos:
        L.append('- ' + tx['md_none'])
    L += ['', f"## {tx['md_how_title']}", '', '> ' + tx['md_how'], '', '---', '',
          f"## {tx['md_weeks_title']}", '', '> ' + tx['md_weeks_note'], '',
          f"| **{tx['md_col_week']}** | **{tx['md_col_vs_week']}** | |", '|:---|---:|:---|']
    complete = wk_tot[:-1] if weeks > 1 else wk_tot
    mean = (sum(complete) / len(complete)) or 1
    tmax = max(wk_tot) or 1
    for k in range(weeks):
        cur = tx['md_in_progress'] if k == weeks - 1 else ''
        L.append(f'| {labels[k]}{cur} | {100 * wk_tot[k] / mean:.0f}% | `{bar(wk_tot[k], tmax)}` |')
    L += ['', f"## {tx['md_days_title']}", '', '> ' + tx['md_days_note'], '',
          f"| **{tx['md_col_day']}** | **{tx['md_col_vs_day']}** | |", '|:---|---:|:---|']
    day_mean = mean / 7
    days = [today - dt.timedelta(days=k) for k in range(13, -1, -1)]
    dmax = max([per_day[d] for d in days] + [1e-9])
    for d in days:
        L.append(f"| {tx['days'][d.weekday()]} {d:%d/%m} | {100 * per_day[d] / day_mean:.0f}% | `{bar(per_day[d], dmax)}` |")
    L += ['', f"## {tx['md_sections_title']}", '',
          f"| **{tx['md_col_section']}** | **{tx['md_col_share']}** | **{tx['md_col_timeline']}** |", '|:---|---:|:---|']
    for p, v in sorted(sections.items(), key=lambda x: -sum(x[1])):
        L.append(f'| {cell(p)} | {pct(sum(v))} | `{sparkline(v)}` |')
    L += ['', f"## {tx['md_threads_title']}", '',
          '| ' + ' | '.join(f'**{c}**' for c in (tx['md_col_thread'], tx['md_col_section'], tx['md_col_share'], tx['md_col_timeline'],
                                                  tx['md_col_relays'], tx['md_col_last'], tx['md_col_type'], tx['md_col_does'],
                                                  'Fable', 'Opus', 'Sonnet', 'Haiku', tx['md_col_reco'])) + ' |',
          '|:---|:---|---:|:---|:---:|:---:|:---|:---:|---:|---:|---:|---:|:---:|']
    for r in rows:
        mods = ' | '.join(f"{100 * r['models'][f]:.0f}%" if r['models'][f] >= 0.005 else '·' for f in FAMILIES)
        mix = '/'.join(f"{100 * r['share'][k]:.0f}" for k in CLASSES)
        mark = tx['md_change_mark'].format(now=r['costly']) if r['saving'] > 0 else ''
        L.append(f"| {cell(r['name'])} | {cell(r['home'])} | {pct(r['total'])} | `{sparkline(r['wk'])}` | {r['relays']} | {r['last']:%d/%m} | "
                 f"{tx['type_' + r['kind']]} | {mix} | {mods} | {r['reco']}{mark}{' · **2**' if r['two'] else ''} |")
    L += ['', '---', '', '*' + tx['md_rule'] + '*', '']
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(L))


def panel_data(rows, weeks, since_list, today, per_day, tx):
    T = sum(r['total'] for r in rows) or 1
    saving = sum(r['saving'] for r in rows)
    wk_tot = [sum(r['wk'][k] for r in rows) for k in range(weeks)]
    complete = wk_tot[:-1] if weeks > 1 else wk_tot
    mean = (sum(complete) / len(complete)) or 1
    norm = lambda v: 100 * v / mean
    day_mean = mean / 7
    labels = [d.strftime('%d/%m') for d in since_list]
    days = [today - dt.timedelta(days=k) for k in range(13, -1, -1)]
    sections = defaultdict(lambda: [0.0] * weeks)
    for r in rows:
        for k in range(weeks):
            sections[r['home']][k] += r['wk'][k]
    secs = []
    for p_, v in sorted(sections.items(), key=lambda x: -sum(x[1])):
        wkn = [norm(x) for x in v]
        secs.append({'name': p_, 'total': 100 * sum(v) / T, 'wkNorm': wkn, 'ult': wkn[-1],
                     'threads': sum(1 for r in rows if r['home'] == p_),
                     'saving': 100 * sum(r['saving'] for r in rows if r['home'] == p_) / T})
    # The page carries only percentages (of the total, or of a normal week), never absolute amounts.
    return {
        'since': f'{since_list[0]:%d/%m/%Y}', 'today': f'{today:%d/%m/%Y}', 'total': 100,
        'saving': 100 * saving / T,
        'wkNow': norm(wk_tot[-1]), 'daysNow': today.weekday() + 1,
        'wkLast': norm(wk_tot[-2]) if weeks > 1 else 0,
        'weeks': [e + (tx['md_in_progress'] if i == weeks - 1 else '') for i, e in enumerate(labels)],
        'days': [[f"{tx['days'][d.weekday()]} {d:%d/%m}", 100 * per_day[d] / day_mean] for d in days],
        'sections': secs,
        'rows': [{
            'id': i, 'name': r['name'], 'section': r['home'], 'total': 100 * r['total'] / T,
            'wkNorm': [norm(x) for x in r['wk']], 'ult': norm(r['wk'][-1]), 'relays': r['relays'],
            'last': f"{r['last']:%d/%m}", 'type': tx['type_' + r['kind']],
            'build': round(100 * r['share']['build']), 'test': round(100 * r['share']['test']),
            'read': round(100 * r['share']['read']), 'coord': round(100 * r['share']['coordinate']),
            'fable': 100 * r['models']['fable'], 'opus': 100 * r['models']['opus'],
            'sonnet': 100 * r['models']['sonnet'], 'haiku': 100 * r['models']['haiku'],
            'reco': r['reco'], 'saving': 100 * r['saving'] / T, 'now': r['now'],
            'diag': tx['diag_' + r['diag']], 'diagKey': r['diag'],
            'rel': [{'date': f"{x['date']:%d/%m}", 'fam': x['fam'], 'cost': 100 * x['cost'] / T,
                     'bt': round(100 * (x['rep']['build'] + x['rep']['test'])), 'read': round(100 * x['rep']['read'])}
                    for x in sorted(r['rel'], key=lambda x: x['date'])],
        } for i, r in enumerate(rows)],
    }


# --------------------------------------------------------------------------- main
def default_logs_dir():
    root = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')
    return os.path.join(root, 'projects')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='threadeyes', description='Spend per Claude Code thread, from your local logs. Nothing leaves your computer.')
    ap.add_argument('--out', default='threadeyes-output', help='folder for the report and the panel (default: ./threadeyes-output)')
    ap.add_argument('--weeks', type=int, help='weeks to cover (default 8)')
    ap.add_argument('--lang', choices=i18n.LANGS, help='language of the output (default: from your system)')
    ap.add_argument('--config', help='optional JSON with your own rules (default: ./threadeyes.json or ~/.threadeyes.json)')
    ap.add_argument('--logs', help='folder with the Claude Code logs (default: ~/.claude/projects)')
    ap.add_argument('--version', action='version', version=f'threadeyes {__version__}')
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # a legacy console must never crash the run on an accent
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass

    try:
        cfg = load_config(find_config(args.config))
        weeks = args.weeks if args.weeks is not None else int(cfg['weeks'])
        re.compile(cfg['relay_pattern'])
    except (ConfigError, ValueError, TypeError, re.error) as e:
        print(f'Config error: {e}', file=sys.stderr)
        return 2
    lang = args.lang or (cfg['language'] if cfg['language'] in i18n.LANGS else i18n.detect_language())
    tx = i18n.texts(lang)
    if weeks < 2:
        ap.error('weeks must be 2 or more (the day-by-day view covers the last two weeks)')
    base = args.logs or default_logs_dir()
    if not os.path.isdir(base):
        print(f"{tx['err_no_logs']} {base}", file=sys.stderr)
        return 2

    today = dt.date.today()
    since_list = [monday(today) - dt.timedelta(weeks=k) for k in range(weeks - 1, -1, -1)]
    since = since_list[0]

    sessions = read_sessions(base, since, cfg, tx)
    threads, per_day = build_threads(sessions, weeks, since, cfg, tx)
    rows = analyse(threads, cfg)
    if not rows:
        print(tx['err_no_data'].format(weeks=weeks, base=base), file=sys.stderr)
        return 3

    os.makedirs(args.out, exist_ok=True)
    write_report(os.path.join(args.out, 'threadeyes-report.md'), rows, weeks, since_list, today, per_day, tx)
    texts = {k: v for k, v in tx.items() if k.startswith('p_')}
    panel.write(os.path.join(args.out, 'threadeyes-panel.html'), panel_data(rows, weeks, since_list, today, per_day, tx), texts, lang)
    T = sum(r['total'] for r in rows) or 1
    print(tx['md_done'].format(n=len(rows), pct=f"{100 * sum(r['saving'] for r in rows) / T:.0f}"))
    print(os.path.abspath(args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())

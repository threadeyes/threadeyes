#!/usr/bin/env python3
"""Make INVENTED Claude Code logs, to try ThreadEyes and to take screenshots without using real data.

Usage:  python examples/make_demo_data.py [folder]      (default: examples/demo-logs)
Then:   python threadeyes.py --logs examples/demo-logs --out examples/demo-output

Everything here is made up: thread names, folders, numbers. The shape of each line is the one
ThreadEyes reads (title, working folder, model, token usage, tool calls). The dates are relative to
today, so the demo always has "the last eight weeks".
"""
import datetime as dt
import json
import os
import random
import sys

# name, working folder, share of work (build, test, read, coordinate), models by period, weekly weight, relay count
THREADS = [
    ('Checkout redesign', 'shop-app', (0.45, 0.25, 0.25, 0.05), ['opus'] * 8, [3, 4, 5, 9, 14, 12, 10, 12], 5),
    ('API migration', 'shop-api', (0.50, 0.35, 0.10, 0.05), ['opus'] * 8, [2, 3, 6, 8, 10, 9, 11, 9], 4),
    ('Architecture review', 'shop-api', (0.05, 0.05, 0.30, 0.10), ['opus'] * 8, [1, 1, 2, 2, 3, 2, 2, 3], 2),
    ('Docs site', 'shop-docs', (0.35, 0.10, 0.45, 0.10), ['sonnet'] * 8, [1, 2, 2, 2, 3, 2, 3, 2], 3),
    ('Bug triage', 'shop-app', (0.15, 0.30, 0.45, 0.10), ['opus', 'opus', 'sonnet', 'sonnet', 'opus', 'sonnet', 'opus', 'sonnet'], [2, 2, 3, 2, 4, 3, 3, 3], 6),
    ('Data cleanup', 'data-tools', (0.40, 0.20, 0.30, 0.10), ['sonnet'] * 8, [0, 1, 1, 2, 2, 1, 1, 2], 2),
    ('Release notes', 'shop-docs', (0.05, 0.05, 0.25, 0.65), ['opus'] * 8, [0, 0, 1, 1, 1, 2, 1, 1], 1),
]
USAGE_PER_TURN = {'opus': (3000, 700, 9000, 60000), 'sonnet': (3000, 800, 9000, 70000)}
MODEL_ID = {'opus': 'claude-opus-5-5', 'sonnet': 'claude-sonnet-5-5'}
TOOLS = {0: [('Edit', {}), ('Write', {})], 1: [('Bash', {'command': 'npm test'}), ('Bash', {'command': 'git status'})],
         2: [('Read', {}), ('Grep', {})], 3: [('TodoWrite', {}), ('Agent', {})]}


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'demo-logs')
    rng = random.Random(7)
    today = dt.date.today()
    start = monday(today) - dt.timedelta(weeks=7)
    n_files = 0
    n_msg = 0
    for name, folder, mix, models, weights, relays in THREADS:
        proj_dir = os.path.join(out, f'demo-{folder}')
        os.makedirs(proj_dir, exist_ok=True)
        # The thread is cut into `relays + 1` sessions over the eight weeks (hand-offs).
        pieces = relays + 1
        for p in range(pieces):
            title = name if p == 0 else f'{name} · relevo {p}'
            w0 = int(p * 8 / pieces)
            w1 = max(w0 + 1, int((p + 1) * 8 / pieces))
            lines = [json.dumps({'customTitle': title, 'cwd': f'/home/demo/{folder}'})]
            for w in range(w0, w1):
                turns = weights[w] * 14
                model = models[w]
                for _ in range(turns):
                    day = start + dt.timedelta(weeks=w, days=rng.choice([0, 1, 2, 3, 4, 5]))
                    if day > today:
                        continue
                    t = dt.datetime.combine(day, dt.time(rng.randint(8, 19), rng.randint(0, 59)), tzinfo=dt.timezone.utc)
                    i, o, cc, cr = USAGE_PER_TURN[model]
                    jitter = rng.uniform(0.6, 1.4)
                    usage = {'input_tokens': int(i * jitter), 'output_tokens': int(o * jitter),
                             'cache_creation_input_tokens': int(cc * jitter), 'cache_read_input_tokens': int(cr * jitter)}
                    content = []
                    if rng.random() < 0.85:
                        k = rng.choices(range(4), weights=mix)[0]
                        tool, inp = rng.choice(TOOLS[k])
                        content.append({'type': 'tool_use', 'name': tool, 'input': inp})
                    # Like the real logs: one line per content block, each repeating the message id and its usage.
                    n_msg += 1
                    blocks = [[{'type': 'text', 'text': 'demo'}]] + ([content] if content else [])
                    for block in blocks:
                        lines.append(json.dumps({'cwd': f'/home/demo/{folder}', 'timestamp': t.isoformat().replace('+00:00', 'Z'),
                                                 'message': {'id': f'msg_demo_{n_msg}', 'role': 'assistant', 'model': MODEL_ID[model],
                                                             'usage': usage, 'content': block}}))
            with open(os.path.join(proj_dir, f'demo-{name.lower().replace(" ", "-")}-{p}.jsonl'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            n_files += 1
    print(f'{n_files} invented session files in {os.path.abspath(out)}')


if __name__ == '__main__':
    main()

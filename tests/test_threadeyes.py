"""Regression tests for ThreadEyes. Invented data only: every log is written to a temporary folder.

Run from the repository folder:   python tests/test_threadeyes.py
They leave nothing behind (no __pycache__, no output files)."""
import sys
sys.dont_write_bytecode = True  # must come before importing anything from the repository

import datetime as dt
import json
import os
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import threadeyes  # noqa: E402

SCRIPT = os.path.join(ROOT, 'threadeyes.py')
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def ts(hours_ago=1.0, at=None):
    t = at or (NOW - dt.timedelta(hours=hours_ago))
    return t.isoformat().replace('+00:00', 'Z')


def msg(mid, model='claude-opus-5-5', tools=(), when=None, usage=None, title=None, cwd='/work/demo-project'):
    """One assistant line as Claude Code writes it."""
    u = usage if usage is not None else {'input_tokens': 100, 'output_tokens': 50,
                                         'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 1000}
    content = [dict(t) for t in tools] or [{'type': 'text', 'text': 'ok'}]
    line = {'type': 'assistant', 'timestamp': when or ts(), 'cwd': cwd,
            'message': {'role': 'assistant', 'id': mid, 'model': model, 'usage': u, 'content': content}}
    if title:
        line['customTitle'] = title
    return line


def tool(tid, name, inp=None):
    return {'type': 'tool_use', 'id': tid, 'name': name, 'input': {} if inp is None else inp}


class Run:
    """Writes logs (and optionally a config), runs ThreadEyes as the user would, and keeps the results."""

    def __init__(self, files, config=None, args=()):
        self.tmp = tempfile.TemporaryDirectory()
        base = self.tmp.name
        self.logs = os.path.join(base, 'logs')
        self.out = os.path.join(base, 'out')
        for rel, lines in files.items():
            path = os.path.join(self.logs, 'proj', rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                for ln in lines:
                    f.write(ln if isinstance(ln, str) else json.dumps(ln))
                    f.write('\n')
        cmd = [sys.executable, '-B', SCRIPT, '--logs', self.logs, '--out', self.out, '--lang', 'en'] + list(args)
        if config is not None:
            cpath = os.path.join(base, 'config.json')
            with open(cpath, 'w', encoding='utf-8') as f:
                f.write(config if isinstance(config, str) else json.dumps(config))
            cmd += ['--config', cpath]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=base)
        self.code, self.stdout, self.stderr = p.returncode, p.stdout, p.stderr
        self.report = self._read('threadeyes-report.md')
        self.panel = self._read('threadeyes-panel.html')

    def _read(self, name):
        path = os.path.join(self.out, name)
        if not os.path.exists(path):
            return None
        with open(path, encoding='utf-8') as f:
            return f.read()

    def data(self):
        m = re.search(r'const D = (\{.*?\});\n', self.panel, re.S)
        return json.loads(m.group(1))

    def close(self):
        self.tmp.cleanup()


class Base(unittest.TestCase):
    def run_te(self, files, config=None, args=()):
        r = Run(files, config, args)
        self.addCleanup(r.close)
        return r

    def assertClean(self, r):
        self.assertEqual(r.code, 0, r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        self.assertEqual(sorted(os.listdir(r.out)), ['threadeyes-panel.html', 'threadeyes-report.md'])


class Robustness(Base):
    """Codex C-06 / ChatGPT TE-02: a malformed block is skipped, the rest of the session still counts."""

    def test_malformed_tool_blocks(self):
        bad = [tool('a', None), tool('b', ['Edit']), tool('c', 'Bash', [1]), tool('d', 'Bash', {'command': 123}),
               {'type': 'tool_use', 'id': 'e', 'name': 'Bash', 'input': 'text'}]
        for i, b in enumerate(bad):
            with self.subTest(block=b):
                r = self.run_te({'s.jsonl': [msg(f'm{i}', tools=[b], title='Docs'), msg(f'n{i}', title='Docs')]})
                self.assertClean(r)
                self.assertEqual(r.data()['rows'][0]['name'], 'Docs')

    def test_broken_lines_and_missing_fields(self):
        lines = ['{not json', '[1, 2]', '"text"', {'type': 'assistant'}, {'message': {'role': 'assistant'}},
                 {'timestamp': 'yesterday', 'message': {'role': 'assistant', 'id': 'x'}}, msg('ok', title='Docs')]
        r = self.run_te({'s.jsonl': lines})
        self.assertClean(r)
        self.assertIn('Not everything could be counted', r.report)

    def test_nan_and_infinite_tokens(self):
        for value in ('NaN', 'Infinity', '-1'):
            with self.subTest(value=value):
                raw = json.dumps(msg('m', title='Docs')).replace('"output_tokens": 50', f'"output_tokens": {value}')
                r = self.run_te({'s.jsonl': [raw, msg('n', title='Docs')]})
                self.assertClean(r)
                self.assertNotIn('nan', r.stdout.lower())
                self.assertNotIn('nan%', r.report.lower())

    def test_integer_too_large_for_a_float(self):
        """Codex, second round: 10**309 as a token count is ignored; as a price it is a clean config error."""
        raw = json.dumps(msg('m', title='Docs')).replace('"input_tokens": 100', '"input_tokens": ' + str(10 ** 309))
        r = self.run_te({'s.jsonl': [raw, msg('n', title='Docs')]})
        self.assertClean(r)
        bad = '{"prices": {"opus": {"in": ' + str(10 ** 309) + '}}}'
        c = self.run_te({'s.jsonl': [msg('m', title='Docs')]}, config=bad)
        self.assertEqual(c.code, 2, c.stderr)
        self.assertNotIn('Traceback', c.stderr)
        self.assertIn('Config error', c.stderr)

    def test_unknown_model_is_declared_once_per_message(self):
        """A message of an unknown model written as three lines (three content blocks) is one message."""
        lines = [msg('m', model='some-new-model', title='Docs', tools=[tool(f't{i}', 'Read')]) for i in range(3)]
        r = self.run_te({'s.jsonl': lines + [msg('n', title='Docs')]})
        self.assertClean(r)
        self.assertIn('1 messages from a model ThreadEyes does not know', r.report)


class Escaping(Base):
    """Codex C-01 and C-05 / ChatGPT TE-10: a thread name shows as text and never becomes markup."""
    NAMES = ['![x](https://example.invalid/leak)', '<img src="https://example.invalid/leak">',
             '<!--<script>', '</script><script>alert(1)</script>', '[a](http://example.invalid) www.example.invalid',
             'a | b', '__DATA__']

    def test_names_are_inert(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                r = self.run_te({'s.jsonl': [msg('m', title=name)]})
                self.assertClean(r)
                rep = r.report
                for active in ('![', '](http', '<img', '<script', '<!--', 'http://', 'https://', 'www.'):
                    self.assertNotIn(active, rep, f'{active!r} left active in the report for {name!r}')
                # Panel: one Chart.js block and one data block, whatever the name.
                self.assertEqual(r.panel.count('<script>'), 2)
                self.assertEqual(r.panel.count('</script>'), 2)
                data_block = r.panel.split('<script>')[2]
                self.assertNotIn('<!--', data_block)
                self.assertNotIn('example.invalid/leak">', data_block)
                self.assertEqual(r.data()['rows'][0]['name'], name)  # the name itself is intact


class Config(Base):
    """Codex C-07: a wrong config stops with a clean message and code 2, and writes nothing."""
    BAD = {
        'projects': {'projects': ['not', 'a', 'map']},
        'aliases': {'aliases': {'Old': 3}},
        'price': {'prices': {'opus': {'out': 'cheap'}}},
        'price_negative': {'prices': {'opus': {'out': -1}}},
        'price_family': {'prices': {'gpt': {'out': 1}}},
        'merge_groups': {'merge_groups': [{'name': 'X', 'contains_all': 'docs'}]},
        'weeks': {'weeks': 'eight'},
        'not_json': '{oops',
    }

    def test_bad_configs(self):
        for case, cfg in self.BAD.items():
            with self.subTest(case=case):
                r = self.run_te({'s.jsonl': [msg('m', title='Docs')]}, config=cfg)
                self.assertEqual(r.code, 2, r.stderr)
                self.assertNotIn('Traceback', r.stderr)
                self.assertIn('Config error', r.stderr)
                self.assertFalse(os.path.exists(r.out))


class Money(Base):
    """Codex C-08 / ChatGPT TE-05 and TE-06."""

    def test_saving_uses_the_users_prices(self):
        files = {'s.jsonl': [msg('m', model='claude-opus-5-5', tools=[tool('t', 'Edit')], title='Build docs')]}
        normal = self.run_te(files)
        self.assertClean(normal)
        self.assertGreater(normal.data()['saving'], 0)
        flipped = self.run_te(files, config={'prices': {'opus': {'out': 1}, 'sonnet': {'out': 10}}})
        self.assertClean(flipped)
        self.assertEqual(flipped.data()['saving'], 0)
        self.assertIn('Simulated saving', flipped.report)

    def test_saving_uses_every_price_not_only_output(self):
        """Codex, second round: 1M input tokens on Opus, no output; input 4 on Opus and 3.8 on Sonnet: 5 %, not 50 %."""
        usage = {'input_tokens': 1_000_000, 'output_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}
        files = {'s.jsonl': [msg('m', model='claude-opus-5-5', usage=usage, tools=[tool('t', 'Edit')], title='Build docs')]}
        r = self.run_te(files, config={'prices': {'opus': {'in': 4}, 'sonnet': {'in': 3.8}}})
        self.assertClean(r)
        self.assertAlmostEqual(r.data()['saving'], 5.0, places=6)

    def test_one_hour_cache_costs_twice_the_input(self):
        five = threadeyes.cost('opus', 'claude-opus-5-5', {'cache_creation_input_tokens': 1_000_000}, threadeyes.DEFAULT_CONFIG)
        hour = threadeyes.cost('opus', 'claude-opus-5-5', {'cache_creation_input_tokens': 1_000_000, 'cache_1h': 1_000_000},
                               threadeyes.DEFAULT_CONFIG)
        self.assertAlmostEqual(five, 5.0)
        self.assertAlmostEqual(hour, 8.0)

    def test_usage_reads_the_one_hour_split(self):
        u = threadeyes.usage_of({'usage': {'cache_creation_input_tokens': 10,
                                           'cache_creation': {'ephemeral_1h_input_tokens': 4, 'ephemeral_5m_input_tokens': 6}}})
        self.assertEqual((u['cache_creation_input_tokens'], u['cache_1h']), (10, 4))


class Counting(Base):
    def test_same_day_model_follows_the_clock_not_the_file_name(self):
        """Codex C-09: Sonnet at 18:00 in a-late.jsonl, Opus at 08:00 in z-early.jsonl: the thread is on Sonnet."""
        day = (NOW - dt.timedelta(days=1)).replace(hour=12)
        late = ts(at=day.replace(hour=18))
        early = ts(at=day.replace(hour=8))
        r = self.run_te({'a-late.jsonl': [msg('m1', model='claude-sonnet-5-5', when=late, title='Docs')],
                         'z-early.jsonl': [msg('m2', model='claude-opus-5-5', when=early, title='Docs')]})
        self.assertClean(r)
        self.assertEqual(r.data()['rows'][0]['now'], 'sonnet')

    def test_resumed_copies_do_not_count_tools_twice(self):
        """ChatGPT TE-03: a resumed session repeats an Edit line; with one Read the split must stay 50/50."""
        edit = msg('m1', tools=[tool('t1', 'Edit')], title='Docs')
        read = msg('m2', tools=[tool('t2', 'Read')], title='Docs')
        r = self.run_te({'first.jsonl': [edit], 'second.jsonl': [edit, read]})
        self.assertClean(r)
        row = r.data()['rows'][0]
        self.assertEqual((row['build'], row['read']), (50, 50))

    def test_cost_of_a_repeated_message_is_counted_once(self):
        """The same message in two files (a resumed session) adds its cost once, not twice."""
        def total(files):
            with tempfile.TemporaryDirectory() as d:
                for name, lines in files.items():
                    os.makedirs(os.path.join(d, 'proj'), exist_ok=True)
                    with open(os.path.join(d, 'proj', name), 'w', encoding='utf-8') as f:
                        f.write('\n'.join(json.dumps(x) for x in lines))
                cov = {'unreadable': 0, 'unknown_model': 0, 'unreadable_files': 0}
                since = dt.date.today() - dt.timedelta(days=30)
                sessions = threadeyes.read_sessions(d, since, threadeyes.DEFAULT_CONFIG, {'other': 'Other'}, cov)
                return sum(n[2] for s in sessions.values() for n in s['notes'])
        one = total({'s.jsonl': [msg('m1', title='Docs'), msg('m2', title='Docs')]})
        two = total({'s.jsonl': [msg('m1', title='Docs'), msg('m2', title='Docs')], 'copy.jsonl': [msg('m1', title='Docs')]})
        self.assertGreater(one, 0)
        self.assertAlmostEqual(one, two)


class Privacy(Base):
    """Codex C-02 and C-10 / ChatGPT TE-01: the files carry no paths; the exact command only goes to the terminal."""

    def test_no_paths_in_outputs_and_full_command_in_terminal(self):
        r = self.run_te({'s.jsonl': [msg('m', title='Docs', cwd='/home/someone/secret-folder/demo-project')]})
        self.assertClean(r)
        for text in (r.panel, r.report):
            for leak in (r.logs, r.out, ROOT, 'secret-folder', 'someone', os.path.expanduser('~')):
                self.assertNotIn(leak, text)
        self.assertNotIn('\\\\', r.data()['cmd'])
        self.assertNotIn('/', r.data()['cmd'])
        last = r.stdout.strip().splitlines()[-1]
        self.assertTrue(last.startswith('To refresh, run:'))
        self.assertIn(sys.executable, last)
        self.assertIn(r.out, last)

    @unittest.skipUnless(os.name == 'nt' and not os.environ.get('MSYSTEM'), 'the command is written for PowerShell only on Windows')
    def test_refresh_command_works_pasted_in_powershell(self):
        """Codex, second round: folders named with $ and ' must survive being pasted into PowerShell."""
        with tempfile.TemporaryDirectory() as d:
            logs = os.path.join(d, "Synthetic $Draft logs")
            out = os.path.join(d, "out `n it's $HOME")
            os.makedirs(os.path.join(logs, 'proj'))
            with open(os.path.join(logs, 'proj', 's.jsonl'), 'w', encoding='utf-8') as f:
                f.write(json.dumps(msg('m', title='Docs')) + '\n')
            p = subprocess.run([sys.executable, '-B', SCRIPT, '--logs', logs, '--out', out, '--lang', 'en'],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(p.returncode, 0, p.stderr)
            command = p.stdout.strip().splitlines()[-1].split('To refresh, run: ', 1)[1]
            report = os.path.join(out, 'threadeyes-report.md')
            os.remove(report)
            ps = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=d)
            self.assertEqual(ps.returncode, 0, ps.stdout + ps.stderr)
            self.assertTrue(os.path.exists(report), 'the pasted command did not rebuild the report in the same folder')

    def test_panel_loads_nothing_from_outside(self):
        r = self.run_te({'s.jsonl': [msg('m', title='Docs')]})
        page = r.panel
        for marker in ('src=', '<link', 'fetch(', 'XMLHttpRequest', 'localStorage', 'sessionStorage', 'sendBeacon',
                       'WebSocket', '@import'):
            self.assertNotIn(marker, page.split('/*! Chart.js')[0] + page.split('</script>', 1)[-1], marker)

    def test_chart_js_licence_is_in_the_panel(self):
        r = self.run_te({'s.jsonl': [msg('m', title='Docs')]})
        self.assertIn('Copyright (c) 2014-2024 Chart.js Contributors', r.panel)
        self.assertIn('Permission is hereby granted, free of charge', r.panel)


class CommandLine(Base):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', SCRIPT] + list(args), capture_output=True, text=True,
                              encoding='utf-8', errors='replace')

    def test_help_and_version(self):
        self.assertEqual(self.run_cli('--help').returncode, 0)
        v = self.run_cli('--version')
        self.assertEqual(v.returncode, 0)
        self.assertIn(threadeyes.__version__, v.stdout)

    def test_invalid_input(self):
        for args in (['--weeks', '1'], ['--weeks', 'x'], ['--weeks', '1000000000000'], ['--lang', 'fr']):
            with self.subTest(args=args):
                p = self.run_cli(*args)
                self.assertEqual(p.returncode, 2)
                self.assertNotIn('Traceback', p.stderr)
        with tempfile.TemporaryDirectory() as d:
            p = self.run_cli('--logs', os.path.join(d, 'missing'), '--out', os.path.join(d, 'out'))
            self.assertEqual(p.returncode, 2)
            self.assertFalse(os.path.exists(os.path.join(d, 'out')))

    def test_both_languages(self):
        for lang in ('en', 'es'):
            with self.subTest(lang=lang):
                r = self.run_te({'s.jsonl': [msg('m', title='Docs')]}, args=['--lang', lang])
                self.assertClean(r)


if __name__ == '__main__':
    unittest.main(verbosity=1)

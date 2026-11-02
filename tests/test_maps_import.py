"""Synthetic public-format regressions; no network, browser or actual saved places."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import venv
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request
from app.domain import Settings, Blocked, eligible
from app.maps_import import (LISTS, Redirects, public_url, preload_url, parse_list,
    nearby_rows, import_lists, ImportedLists, fetch_public, _fetch_direct, restaurant, BrowserCategories)
from app.maps_categories import category_from_primary

ROOT = Path(__file__).resolve().parents[1]
SPECS = (('One', 'https://maps.app.goo.gl/one', 'list-one', 1),
         ('Two', 'https://maps.app.goo.gl/two', 'list-two', 1))


def entry(cid='42', lat=37.55, address='1 Synthetic Street'):
    return [None, [None, None, None, None, address, [None, None, lat, -122.31], ['1', cid]], 'Synthetic Place']


def raw(spec, entries=None):
    data = [None] * 21
    data[0] = [spec[2]]
    data[4] = spec[0]
    data[8] = entries if entries is not None else [entry()]
    data[12] = spec[3]
    return [data, '', None, None, None, None, None]


def metadata(row, label='Japanese restaurant'):
    return dict(cid=row['id'], name=row['name'], category=label,
                final_url=row['maps_url'], status='verified_public_category')


class MapsImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'snapshot.json'
        self.settings = Settings.load(ROOT / 'tests/fixtures/two-list-settings.json')
        self.settings=replace(self.settings,lists=tuple((spec[0],reference) for spec,(_,reference) in zip(SPECS,self.settings.lists)))
        self.responses = {}
        for spec in SPECS:
            endpoint = 'https://www.google.com/maps/preview/entitylist/getlist?pb=!1s'+spec[2]+'!4i10000!6b1'
            self.responses[spec[1]] = '<link href="'+endpoint.replace('10000', '500')+'">'
            self.responses[endpoint] = json.dumps(raw(spec))

    def fetch(self, url):
        return self.responses[url]

    def test_both_complete_atomic_import_and_dedup_preserves_sources(self):
        calls = []
        def classify(row):
            calls.append(row['id'])
            return metadata(row)
        result = import_lists(self.settings, classify, self.output, self.fetch, SPECS)
        self.assertEqual([e['count'] for e in result['evidence']], [1, 1])
        self.assertEqual(result['unique_restaurants'], 1)
        self.assertEqual(calls, ['42'])
        with patch('app.maps_import.LISTS', SPECS):
            source = ImportedLists(self.output, self.settings)
            places = [p for spec in SPECS for p in source.fetch(spec[0], None).places]
        self.assertEqual(eligible(places, self.settings)[0].sources, ('One', 'Two'))

    def test_removed_added_or_inconsistent_restaurant_rows_fail_completeness(self):
        payload=import_lists(self.settings,metadata,self.output,self.fetch,SPECS)
        for change in ['removed','added','boolean','bounds']:
            with self.subTest(change=change):
                data=json.loads(json.dumps(payload))
                if change=='removed':data['lists']['One'].pop()
                elif change=='added':data['lists']['One'].append(dict(data['lists']['One'][0]))
                elif change=='boolean':data['evidence'][0]['restaurants']=True
                else:data['evidence'][0]['nearby']=data['evidence'][0]['count']+1
                self.output.write_text(json.dumps(data))
                with patch('app.maps_import.LISTS',SPECS),self.assertRaises(Blocked):
                    ImportedLists(self.output,self.settings)

    def test_second_list_failure_preserves_prior_snapshot(self):
        self.output.write_text('prior complete snapshot')
        self.responses[SPECS[1][1]] = 'List unavailable'
        with self.assertRaises(ValueError):
            import_lists(self.settings, metadata, self.output, self.fetch, SPECS)
        self.assertEqual(self.output.read_text(), 'prior complete snapshot')
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_count_identity_continuation_and_schema_drift_fail(self):
        for mutate in (lambda r: r[0].__setitem__(12, 2),
                       lambda r: r[0].__setitem__(4, 'Foreign list'),
                       lambda r: r[0][0].__setitem__(0, 'foreign-id'),
                       lambda r: r.__setitem__(1, 'next-page'),
                       lambda r: r[0].__setitem__(8, []),
                       lambda r: r.append(None)):
            data = raw(SPECS[0]); mutate(data)
            with self.assertRaises(ValueError): parse_list(json.dumps(data), SPECS[0])
        self.assertEqual(len(parse_list(")]}'\n"+json.dumps(raw(SPECS[0])), SPECS[0])), 1)

    def test_complete_list_growth_uses_current_reported_total(self):
        for spec in SPECS:
            data = raw(spec, [entry(), entry(cid='43')])
            data[0][12] = 2  # Historical spec count remains one.
            self.assertEqual(len(parse_list(json.dumps(data), spec)), 2)
            self.responses[preload_url(self.responses[spec[1]])] = json.dumps(data)
        result = import_lists(self.settings, metadata, self.output, self.fetch, SPECS)
        self.assertEqual([e['expected'] for e in result['evidence']], [2, 2])
        with patch('app.maps_import.LISTS', SPECS):
            source = ImportedLists(self.output, self.settings)
            self.assertEqual(len(source.fetch('One', None).places), 2)
            tampered = json.loads(self.output.read_text())
            tampered['evidence'][0]['count'] = 1
            self.output.write_text(json.dumps(tampered))
            with self.assertRaises(Blocked):
                ImportedLists(self.output, self.settings)
        partial = raw(SPECS[0])
        partial[0][12] = 2
        with self.assertRaises(ValueError):
            parse_list(json.dumps(partial), SPECS[0])

    def test_missing_coordinates_address_and_deleted_feature_block(self):
        for mutate in (lambda e: e[1].__setitem__(5, None),
                       lambda e: e[1].__setitem__(6, None),
                       lambda e: e[1][5].__setitem__(2, float('nan'))):
            item = entry(); mutate(item)
            with self.assertRaises(ValueError): nearby_rows([item], self.settings)
        for spec in SPECS:
            endpoint = preload_url(self.responses[spec[1]])
            self.responses[endpoint] = json.dumps(raw(spec, [entry(address='')]))
        with self.assertRaises(ValueError):
            import_lists(self.settings, metadata, self.output, self.fetch, SPECS)
        repaired = import_lists(self.settings, lambda r: dict(metadata(r), address='2 Public Street'),
                                self.output, self.fetch, SPECS)
        self.assertEqual(repaired['unique_restaurants'], 1)
        distant = entry(lat=0, address='')
        distant[1][6] = None
        self.assertEqual(nearby_rows([distant], self.settings), [])

    def test_category_absence_or_identity_mismatch_never_silently_skips(self):
        for classify in (lambda r: {}, lambda r: metadata(dict(r, id='999')),
                         lambda r: dict(metadata(r), category='')):
            with self.assertRaises(ValueError):
                import_lists(self.settings, classify, self.output, self.fetch, SPECS)
            self.assertFalse(self.output.exists())

    def test_nonrestaurant_excluded_without_using_name_or_nested_restaurants(self):
        result = import_lists(self.settings, lambda r: metadata(r, '5-star hotel'),
                              self.output, self.fetch, SPECS)
        self.assertEqual(result['unique_restaurants'], 0)
        self.assertFalse(restaurant('Restaurant supply store'))
        self.assertFalse(restaurant('Cafe'))
        self.assertTrue(restaurant('Northern Italian restaurant'))
        self.assertEqual(category_from_primary('Synthetic Hotel\n5-star hotel\nOverview\nAt this place\nSeafood restaurant'), '5-star hotel')
        with self.assertRaises(ValueError): category_from_primary('Hotel\nOverview\n5-star hotel')

    def test_html_unescape_encoded_limit_and_foreign_redirects(self):
        url = preload_url('<link href="https://www.google.com/maps/preview/entitylist/getlist?pb=%211sx%214i500%216b1&amp;hl=en">')
        self.assertIn('%214i10000', url)
        self.assertIn('&hl=en', url)
        for foreign in ('http://www.google.com/maps', 'https://evil.test/maps',
                        'https://www.google.com.evil.test/maps', 'https://www.google.com:444/maps',
                        'https://user@www.google.com/maps'):
            with self.assertRaises(ValueError): public_url(foreign)
            with self.assertRaises(ValueError):
                Redirects().redirect_request(Request(SPECS[0][1]), None, 302, '', {}, foreign)
        with self.assertRaises(ValueError): preload_url('<html>unavailable</html>')

    def test_public_reads_retry_three_times_without_fallback(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=URLError('offline')) as call, patch('app.maps_import.time.sleep'):
            with self.assertRaises(Blocked): _fetch_direct(SPECS[0][1])
        self.assertEqual(call.call_count, 3)

    def test_public_read_transient_failure_retries_then_returns_complete_body(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.url = SPECS[0][1]
        response.read.return_value = b'complete synthetic response'
        response.length = 0
        with patch('urllib.request.OpenerDirector.open', side_effect=[URLError('transient'), response]) as call, patch('app.maps_import.time.sleep'):
            self.assertEqual(_fetch_direct(SPECS[0][1]), 'complete synthetic response')
        self.assertEqual(call.call_count, 2)

    def test_missing_imported_snapshot_blocks_preview_without_fixture_fallback(self):
        from app.cli import main
        from contextlib import redirect_stdout
        from io import StringIO
        configured = replace(self.settings, maps_snapshot=str(self.output),
                             state_path=str(self.output.parent / 'weekly.db'))
        with patch('sys.argv', ['run', 'preview']), patch('app.cli.Settings.load', return_value=configured), patch('app.cli.run') as run, redirect_stdout(StringIO()) as output:
            self.assertEqual(main(), 1)
        run.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['status'], 'blocked')
        self.assertFalse((self.output.parent / 'weekly.db').exists())

    def test_tampered_snapshot_category_and_scope_are_blocked(self):
        import_lists(self.settings, metadata, self.output, self.fetch, SPECS)
        with patch('app.maps_import.LISTS', SPECS):
            with self.assertRaises(Blocked): ImportedLists(self.output, replace(self.settings, radius_miles=14))
            result = json.loads(self.output.read_text())
            result['categories']['42']['category'] = 'Hotel'
            self.output.write_text(json.dumps(result))
            with self.assertRaises(Blocked): ImportedLists(self.output, self.settings)

    def test_different_preload_list_blocks_before_payload_request(self):
        self.responses[SPECS[0][1]] = self.responses[SPECS[1][1]]
        with self.assertRaises(ValueError):
            import_lists(self.settings, metadata, self.output, self.fetch, SPECS)
        self.assertFalse(self.output.exists())

    def test_browser_failure_leaves_output_unchanged(self):
        import subprocess
        with patch('app.maps_import.bounded_process', side_effect=subprocess.TimeoutExpired('browser', 50)):
            classify = BrowserCategories('/usr/bin/python3')
            with self.assertRaises(Blocked):
                import_lists(self.settings, classify, self.output, self.fetch, SPECS)
        self.assertFalse(self.output.exists())

    def test_missing_browser_and_dependency_failures_preserve_prior_snapshot(self):
        import subprocess
        with self.assertRaises(Blocked):
            BrowserCategories(self.output.parent / 'not-installed-python')
        for error in (FileNotFoundError('missing interpreter'),
                      ValueError('Public data helper failed'),
                      subprocess.TimeoutExpired('browser', 50)):
            self.output.write_text('prior complete snapshot')
            with patch('app.maps_import.bounded_process', side_effect=error):
                with self.assertRaises(Blocked):
                    import_lists(self.settings, BrowserCategories('/usr/bin/python3'),
                                 self.output, self.fetch, SPECS)
            self.assertEqual(self.output.read_text(), 'prior complete snapshot')

    def test_partial_category_success_and_wrong_place_reply_preserve_snapshot(self):
        spec = SPECS[1]
        self.responses[preload_url(self.responses[spec[1]])] = json.dumps(raw(spec, [entry(cid='43')]))
        self.output.write_text('prior complete snapshot')
        def classify(row):
            if row['id'] == '43':
                raise Blocked('Primary heading remained ambiguous')
            return metadata(row)
        with self.assertRaises(Blocked):
            import_lists(self.settings, classify, self.output, self.fetch, SPECS)
        self.assertEqual(self.output.read_text(), 'prior complete snapshot')
        for url in ('https://www.google.com/maps?cid=99', 'https://evil.test/maps?cid=42'):
            with patch('app.maps_import.bounded_process', return_value=json.dumps(
                    dict(metadata(dict(id='42', name='Synthetic Place', maps_url=url))))):
                with self.assertRaises(Blocked):
                    BrowserCategories('/usr/bin/python3')(dict(id='42', name='Synthetic Place'))
            with self.assertRaises(ValueError):
                import_lists(self.settings, lambda row: dict(metadata(row), final_url=url),
                             self.output, self.fetch, SPECS)
            self.assertEqual(self.output.read_text(), 'prior complete snapshot')

    def test_symlinked_venv_helper_keeps_its_python_environment(self):
        from app.maps_import import bounded_process
        environment = Path(self.temp.name) / 'category-venv'
        venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
        interpreter = environment / 'bin' / 'python'
        self.assertTrue(interpreter.is_symlink())
        classifier = BrowserCategories(interpreter)
        # Exercise the actual subprocess boundary, without Playwright or network.
        # The old resolve() implementation reports the base prefix here.
        result = json.loads(bounded_process(
            [classifier.python, '-B', '-c',
             'import json,sys; print(json.dumps([sys.prefix, sys.base_prefix]))'], '', 10))
        self.assertEqual(Path(result[0]).resolve(), environment.resolve())
        self.assertNotEqual(Path(result[0]).resolve(), Path(result[1]).resolve())

    def test_preview_action_cannot_construct_slack_even_from_live_configuration(self):
        from app.cli import main
        from contextlib import redirect_stdout
        from io import StringIO
        config = json.loads((ROOT / 'tests/fixtures/two-list-settings.json').read_text())
        config.update(mode='live', slack_channel='C0CCRQUR6G1', state_path=str(self.output.parent / 'weekly.db'))
        for item, original in zip(config['lists'], self.settings.lists):
            item['file'] = original[1]
        path = self.output.parent / 'config.json'
        path.write_text(json.dumps(config))
        with patch('sys.argv', ['run', 'preview', '--config', str(path), '--now', '2026-10-29T10:00:00-07:00']), patch('app.broker_slack.BrokerSlack') as slack, redirect_stdout(StringIO()) as output:
            self.assertEqual(main(), 0)
        slack.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['status'], 'previewed')
        self.assertFalse((self.output.parent / 'weekly.db').exists())

    def test_watch_bounds_consecutive_prerequisite_failures(self):
        from app.cli import main
        from contextlib import redirect_stdout
        from io import StringIO
        configured = replace(self.settings, state_path=str(self.output.parent / 'watch.db'))
        with patch('sys.argv', ['run', 'watch']), patch('app.cli.Settings.load', return_value=configured), patch('app.cli.run', side_effect=Blocked('offline')) as call, patch('app.cli.time.sleep') as sleep, redirect_stdout(StringIO()):
            self.assertEqual(main(), 1)
        self.assertEqual(call.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [120, 240])


class PrimaryHeadingTests(unittest.TestCase):
    """DOM loading sequences and a virtual clock; no Playwright dependency."""
    def sample(self, headings=None, **changes):
        result = dict(url='https://www.google.com/maps?cid=42&hl=en',
                      headings=['Synthetic Place'] if headings is None else headings,
                      categories=['Japanese restaurant'], addresses=['Address: 1 Synthetic Street'], body='')
        result.update(changes)
        return result

    def read(self, sequence, url='https://www.google.com/maps?cid=42'):
        from app.maps_categories import primary_metadata
        class Page:
            def __init__(self):
                self.url = url
                self.calls = 0
            def evaluate(self, script):
                item = sequence[min(self.calls, len(sequence)-1)]
                self.calls += 1
                if isinstance(item, Exception):
                    raise item
                return item
        self.page = Page()
        self.elapsed = 0
        def sleep(seconds):
            self.elapsed += seconds
        with patch('app.maps_categories.time.monotonic', side_effect=lambda: self.elapsed), \
                patch('app.maps_categories.time.sleep', side_effect=sleep):
            return primary_metadata(self.page, '42')

    def test_transient_missing_duplicate_empty_and_replaced_headings_stabilize(self):
        result = self.read([self.sample([]), self.sample(['Loading', 'Synthetic Place']),
                            self.sample(['']), RuntimeError('Execution context destroyed'),
                            self.sample(['Old heading']), self.sample(), self.sample(), self.sample()])
        self.assertEqual(self.page.calls, 8)
        self.assertEqual(result['place_name'], 'Synthetic Place')
        self.assertEqual(result['category'], 'Japanese restaurant')
        self.assertEqual(result['address'], '1 Synthetic Street')

    def test_persistent_missing_ambiguous_or_empty_heading_is_bounded(self):
        for headings in ([], [''], ['One', 'Two']):
            with self.subTest(headings=headings), self.assertRaises(ValueError):
                self.read([self.sample(headings)])
            self.assertLessEqual(self.page.calls, 61)
            self.assertEqual(self.elapsed, 12)

    def test_persistent_single_loading_heading_is_bounded(self):
        for heading in ('Loading', 'Loading...', 'Loading\u2026', '  LOADING . . .  '):
            with self.subTest(heading=heading), self.assertRaises(ValueError):
                self.read([self.sample([heading])])
            self.assertLessEqual(self.page.calls, 61)
            self.assertEqual(self.elapsed, 12)

    def test_single_loading_heading_then_valid_metadata_stabilizes(self):
        result = self.read([self.sample(['Loading'])] * 3 + [self.sample()] * 3)
        self.assertEqual(self.page.calls, 6)
        self.assertEqual(result['place_name'], 'Synthetic Place')
        self.assertEqual(result['category'], 'Japanese restaurant')
        self.assertEqual(result['address'], '1 Synthetic Street')

    def test_loading_heading_resets_existing_stability_streak(self):
        result = self.read([self.sample()] * 2 + [self.sample(['Loading'])]
                           + [self.sample()] * 3)
        self.assertEqual(self.page.calls, 6)
        self.assertEqual(result['place_name'], 'Synthetic Place')

    def test_metadata_and_heading_must_stabilize_together(self):
        sequence = [self.sample(['One']), self.sample(['Two'])] * 31
        with self.assertRaises(ValueError):
            self.read(sequence)
        for changes in (dict(categories=[]), dict(categories=['Restaurant', 'Hotel']),
                        dict(categories=['']), dict(addresses=['Address: One', 'Address: Two'])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.read([self.sample(**changes)])

    def test_persistent_execution_context_failure_is_bounded(self):
        with self.assertRaises(ValueError):
            self.read([RuntimeError('Execution context destroyed')])
        self.assertEqual(self.elapsed, 12)

    def test_foreign_redirect_or_changed_cid_never_supplies_metadata(self):
        foreign = ('https://evil.test/maps?cid=42', 'https://www.google.com/maps?cid=99',
                   'https://www.google.com/maps?cid=42&cid=99',
                   'https://www.google.com:444/maps?cid=42',
                   'https://user@www.google.com/maps?cid=42',
                   'https://www.google.com/maps-other?cid=42')
        for url in foreign:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.read([self.sample()], url=url)
            self.assertEqual(self.page.calls, 0)
            with self.assertRaises(ValueError):
                self.read([self.sample(), self.sample(), self.sample(url=url)])
            self.assertEqual(self.page.calls, 3)

    def test_hotel_primary_fallback_remains_nonrestaurant(self):
        result = self.read([self.sample(categories=[], body='Synthetic Hotel\n5-star hotel\nOverview\nRestaurant')])
        self.assertEqual(result['category'], '5-star hotel')

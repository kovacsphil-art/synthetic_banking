"""Build the closed Pages artifact from one validated report and optional gated preview.

No Databricks access, row-file discovery, Release uploads or publication authorization.
"""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.publish_showcase import ROOT, validate_report

STATIC_FILES = (
    'index.html', 'styles.css', 'results.js', 'validation.html', 'validation.js',
    'validation-config.js', 'executive-viz.js', 'showcase.js', 'records.js',
    'records-config.js', 'downloads.js',
)
DEMO_FILES = ('demo-preview.json', 'dataset-downloads.json')


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'script' and 'src' in attributes:
            self.assets.append(attributes['src'])
        if tag == 'link' and 'stylesheet' in attributes.get('rel', '').split():
            self.assets.append(attributes.get('href', ''))


def _file(source, name, maximum):
    path = source / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source.resolve()) or path.stat().st_size > maximum:
        raise ValueError('Required public asset is missing, linked or oversized.')
    return path.read_bytes()


def _demo(source, report):
    from jsonschema import Draft202012Validator, FormatChecker
    raw = {name: _file(source, name, 96*1024 if name == 'demo-preview.json' else 16*1024) for name in DEMO_FILES}
    preview, manifest = (json.loads(raw[name]) for name in DEMO_FILES)
    for value, schema in ((preview, 'demo-preview.schema.json'), (manifest, 'dataset-downloads.schema.json')):
        contract = json.loads((ROOT / 'docs/reporting' / schema).read_bytes())
        if not Draft202012Validator(contract, format_checker=FormatChecker()).is_valid(value):
            raise ValueError('Public demo metadata does not match its closed schema.')
    reference = report.get('demo_dataset')
    if (manifest['publication_status'] != 'PUBLISHED' or
            {key:manifest[key] for key in ('dataset_version','release_mode','preview_sha256')} != reference or
            hashlib.sha256(raw['demo-preview.json']).hexdigest() != manifest['preview_sha256'] or
            preview['dataset_version'] != manifest['dataset_version'] or
            preview['privacy_status'] != manifest['privacy_status'] or
            report.get('privacy',{}).get('status') != manifest['privacy_status']):
        raise ValueError('Report, preview and verified demo manifest differ.')
    counts = {row['table']:row['value'] if row['status']=='AVAILABLE' else None for row in report['generation']['table_rows']}
    for table in preview['tables']:
        asset = next(a for a in manifest['assets'] if a['key'] == table['name'])
        if asset['rows'] != table['total_rows'] or asset['rows'] != counts.get(table['name']):
            raise ValueError('Demo counts differ from the selected generation.')
    expected = {a['key']:'https://github.com/'+manifest['repository']+'/releases/download/'+manifest['dataset_version']+'/'+a['file'] for a in manifest['assets']}
    if manifest.get('download_urls') != expected:
        raise ValueError('Demo URLs must identify the exact published version.')
    return raw


def stage_site(source, destination, *, include_demo=False):
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Use a new empty staging destination.')
    report = validate_report(_file(source, 'latest-pipeline.json', 1024*1024))
    files = {name:_file(source, name, 512*1024) for name in STATIC_FILES}
    for name in ('index.html', 'validation.html'):
        references = AssetReferences();references.feed(files[name].decode('utf-8'))
        paths = set()
        for value in references.assets:
            url = urlsplit(value)
            if url.scheme or url.netloc or url.path not in STATIC_FILES or url.fragment:
                raise ValueError('HTML references an asset outside the static package.')
            paths.add(url.path)
        required = set(STATIC_FILES)-{'index.html','validation.html'} if name=='index.html' else {'styles.css','validation.js','validation-config.js','executive-viz.js'}
        if not required.issubset(paths):
            raise ValueError('HTML is missing required report/explorer assets.')
    # Re-serialize the sanitized projection: never copy incoming free-text warnings.
    files['latest-pipeline.json'] = (json.dumps(report, indent=2, allow_nan=False)+'\n').encode('utf-8')
    if include_demo:
        files.update(_demo(source, report))
    files['.nojekyll'] = b''
    destination.mkdir(parents=True)
    for name, data in files.items():
        (destination / name).write_bytes(data)
    if {p.name for p in destination.iterdir()} != set(files):
        raise ValueError('Unexpected content in the Pages artifact.')
    return dict(status='PASS', files=len(files), demo_metadata_included=include_demo,
                report_sha256=hashlib.sha256(files['latest-pipeline.json']).hexdigest())


def main():
    result = stage_site(ROOT/'docs', ROOT/'_site', include_demo=os.environ.get('DEMO_READY') == 'true')
    print(json.dumps(result))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write('### Publication checks passed\n\nOne validated report; exact static-asset allowlist; '
                         +'matching gated demo metadata: '+str(result['demo_metadata_included']).lower()+'.\n\n'
                         +'Sanitized report SHA-256: `'+result['report_sha256']+'`\n')


if __name__ == '__main__':
    # Allow direct invocation from the repository root without installing a package.
    try:
        main()
    except Exception:
        print('Pages artifact check failed; existing deployment retained.', file=sys.stderr)
        sys.exit(1)

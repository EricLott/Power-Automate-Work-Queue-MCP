"""Summarize PAC FetchXML importjob output without printing the full report."""
import argparse
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET


def summarize(text):
    reports = []
    for xml in re.findall(r'<importexportxml\b.*?</importexportxml>', text, re.S):
        root = ET.fromstring(xml)
        failures = []
        for parent in root.iter():
            for result in parent:
                if result.tag == 'result' and result.get('result') != 'success':
                    failures.append({
                        'componentType': parent.tag,
                        'component': parent.get('id', parent.get('LocalizedName', '')),
                        'code': result.get('errorcode'),
                        'message': result.get('errortext'),
                    })
        reports.append({'failures': failures})
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.file.read_text(encoding='utf-8-sig')), indent=2))

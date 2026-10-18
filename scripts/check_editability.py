#!/usr/bin/env python3
"""輸出原生文字、表格、圖片與備註清單；物件數不是視覺驗收。"""
import argparse
import json
from workflow import audit_deck,cli_error
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('deck');p.add_argument('--expected-slides',type=int);a=p.parse_args()
    try:
        report=audit_deck(a.deck)
        if a.expected_slides is not None and report['slideCount']!=a.expected_slides:raise ValueError('頁數不符。')
        print(json.dumps(report,ensure_ascii=False,indent=2));return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())

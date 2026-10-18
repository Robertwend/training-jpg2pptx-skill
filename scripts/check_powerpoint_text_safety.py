#!/usr/bin/env python3
"""以命名空間檢查投影片、版面與母片，不依賴 XML 前綴。"""
import argparse
from workflow import audit_deck,cli_error
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('deck');a=p.parse_args()
    try:audit_deck(a.deck);print('通過：沒有延遲自動適配標記，封裝關聯完整。');return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())

"""Writes each domain's URLs to out/<domain>/urls.txt.gz and a report.json with
counts by source and type. Keyed by spider so many domains can run at once."""
import gzip
import json
import os
from collections import Counter


class DedupGzipPipeline:
    def open_spider(self, spider):
        if not hasattr(self, "state"):
            self.state = {}
        out_dir = os.path.join("out", spider.domain)
        os.makedirs(out_dir, exist_ok=True)
        self.state[spider] = {
            "fh": gzip.open(os.path.join(out_dir, "urls.txt.gz"), "wt", encoding="utf-8"),
            "dir": out_dir,
            "by_source": Counter(),
            "by_type": Counter(),
            "total": 0,
        }

    def process_item(self, item, spider):
        st = self.state[spider]
        st["fh"].write(item["url"] + "\n")
        st["by_source"][item["source"]] += 1
        st["by_type"][item["url_type"]] += 1
        st["total"] += 1
        return item

    def close_spider(self, spider):
        st = self.state.pop(spider)
        st["fh"].close()
        report = {
            "domain": spider.domain,
            "total_unique_urls": st["total"],
            "by_source": dict(st["by_source"]),
            "by_type": dict(st["by_type"]),
        }
        with open(os.path.join(st["dir"], "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        spider.logger.info("DONE %s: %s", spider.domain, report)

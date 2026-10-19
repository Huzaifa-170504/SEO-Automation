
import asyncio
import json

from app.agents.website_auditor import WebsiteAuditor


async def main():
    auditor = WebsiteAuditor(
        timeout=25.0,
        max_pages=5000,
        delay_seconds=0.5,
    )

    print("Starting full discoverable website audit...")
    print("Website: https://zeetech.pro/")
    print("Maximum pages: 5000")
    print("Please wait; this may take some time.")

    report = await auditor.audit("https://zeetech.pro/")

    output_path = auditor.save_report(report, "data/reports/manual_audit.json")

    print("\n========== AUDIT SUMMARY ==========")
    print("Website:", report["website"])
    print("Pages crawled:", report["pages_crawled"])
    print("Crawl limit reached:", report["crawl_limit_reached"])
    print("Sitemaps found:", len(report["sitemaps_found"]))
    print("Errors:", report["errors_count"])
    print("Report saved:", output_path)

    print("\n========== PAGE ISSUES ==========")

    for page in report["pages"]:
        if page["issues"]:
            print(f"\n{page['url']}")
            for issue in page["issues"]:
                print(" -", issue)

    print("\nAudit finished.")


if __name__ == "__main__":
    asyncio.run(main())

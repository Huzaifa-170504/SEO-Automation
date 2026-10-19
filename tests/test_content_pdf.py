from app.services.content_pdf import build_content_pdf


def test_content_report_is_a_pdf_with_expected_filename() -> None:
    report = build_content_pdf(
        {
            "job_id": 12,
            "status": "approved",
            "website": "https://example.com",
            "primary_keyword": "technical SEO",
            "strategy": {
                "recommended_word_count": 900,
                "competitor_research": [
                    {"url": "https://competitor.example", "title": "SEO Guide"}
                ],
            },
            "drafts": [
                {
                    "version": 1,
                    "word_count": 850,
                    "content": {"title": "SEO Guide", "body": "Useful article body."},
                }
            ],
            "reviews": [{"status": "approved", "issues": []}],
            "final_content": {"title": "SEO Guide", "body": "Final article."},
        }
    )

    assert report.name == "content_12_results.pdf"
    assert report.getvalue().startswith(b"%PDF")

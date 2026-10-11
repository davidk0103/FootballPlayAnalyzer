"""Job task types and the Celery task that executes each one.

Every type runs through the same runner (lease, attempts, retries, cancellation); the
separate Celery task names exist so each type can be routed, rate limited, or scaled
independently later without changing the job model.
"""

IMPORT_SEASON = "import_season"
IMPORT_UPLOAD = "import_upload"
GENERATE_REPORT = "generate_report"
EXPORT_REPORT = "export_report"

# Season imports change public data, so their jobs are visible to everyone.
PUBLIC_TASK_TYPES = frozenset({IMPORT_SEASON})

TASK_NAMES: dict[str, str] = {
    IMPORT_SEASON: "playbookiq.run_import_job",
    IMPORT_UPLOAD: "playbookiq.process_upload",
    GENERATE_REPORT: "playbookiq.generate_report",
    EXPORT_REPORT: "playbookiq.export_report",
}
REAP_TASK = "playbookiq.reap_stale_jobs"

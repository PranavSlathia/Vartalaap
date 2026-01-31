from arq import cron


async def send_whatsapp_followup(ctx):
    return None


async def process_transcript(ctx):
    return None


async def purge_old_records(ctx):
    return None


async def retry_failed_whatsapp(ctx):
    return None


class WorkerSettings:
    functions = [send_whatsapp_followup, process_transcript]
    cron_jobs = [
        cron(purge_old_records, hour=3, minute=0),
        cron(retry_failed_whatsapp, minute=0),
    ]

import os
from api4jenkins import Jenkins
from api4jenkins.queue import QueueItem
from api4jenkins.build import Build
import logging
import json
from time import time, sleep
import signal
import sys

log_level = os.environ.get("INPUT_LOG_LEVEL", "INFO")
logging.basicConfig(format="JENKINS_ACTION: %(message)s", level=log_level)


def register_queue_item_cancel(
    queue_item: QueueItem
) -> None:
    def signal_handler(sig, frame):
        print("Stopping queued build")
        queue_item.cancel()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)


def register_build_item_cancel(
    build: Build
) -> None:
    def signal_handler(sig, frame):
        print("Stopping build")
        build.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)


def run(
    url: str,
    job_name: str,
    username: str | None,
    api_token: str | None,
    parameters: str | None,
    cookies: str | None,
    wait: bool,
    timeout: int,
    start_timeout: int,
    interval: int,
    cancel_jenkins_run_on_gh_cancel: bool,
):
    if username and api_token:
        auth = (username, api_token)
    else:
        auth = None
        logging.info(
            "Username or token not provided. Connecting without authentication."
        )  # noqa

    if parameters:
        try:
            parameters = json.loads(parameters)
        except json.JSONDecodeError as e:
            raise Exception("`parameters` is not valid JSON.") from e
    else:
        parameters = {}

    if cookies:
        try:
            cookies = json.loads(cookies)
        except json.JSONDecodeError as e:
            raise Exception("`cookies` is not valid JSON.") from e
    else:
        cookies = {}

    jenkins = Jenkins(url, auth=auth, cookies=cookies)

    try:
        jenkins.version
    except Exception as e:
        raise Exception("Could not connect to Jenkins.") from e

    logging.info("Successfully connected to Jenkins.")

    queue_item = jenkins.build_job(job_name, **parameters)

    logging.info("Requested to build job.")

    if cancel_jenkins_run_on_gh_cancel:
        register_queue_item_cancel(queue_item)

    t0 = time()
    sleep(interval)
    while time() - t0 < start_timeout:
        build = queue_item.get_build()
        if build:
            break
        logging.info(f"Build not started yet. Waiting {interval} seconds.")
        sleep(interval)
    else:
        raise Exception(
            f"Could not obtain build and timed out. Waited for {start_timeout} seconds."
        )  # noqa

    build_url = build.url
    logging.info(f"Build URL: {build_url}")
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(f"build_url={build_url}", file=fh)

    # Output as markdown so it's clickable!
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
        print(f"The build URL is: [{build_url}]({build_url})", file=fh)

    print(f"::notice title=build_url::{build_url}")

    if cancel_jenkins_run_on_gh_cancel:
        register_build_item_cancel(build)

    if not wait:
        logging.info("Not waiting for build to finish.")
        return

    t0 = time()
    sleep(interval)
    while time() - t0 < timeout:
        result = build.result
        if result == "SUCCESS":
            logging.info("Build successful 🎉")
            return
        elif result in ("FAILURE", "ABORTED", "UNSTABLE"):
            raise Exception(f'Build status returned "{result}". Build has failed ☹️.')
        logging.info(f"Build not finished yet. Waiting {interval} seconds. {build_url}")
        sleep(interval)
    else:
        raise Exception(
            f"Build has not finished and timed out. Waited for {timeout} seconds."
        )  # noqa


def main():
    # Required
    url = os.environ["INPUT_URL"]
    job_name = os.environ["INPUT_JOB_NAME"]

    # Optional
    username = os.environ.get("INPUT_USERNAME")
    api_token = os.environ.get("INPUT_API_TOKEN")
    parameters = os.environ.get("INPUT_PARAMETERS")
    cookies = os.environ.get("INPUT_COOKIES")
    wait = bool(os.environ.get("INPUT_WAIT"))
    timeout = int(os.environ.get("INPUT_TIMEOUT"))
    start_timeout = int(os.environ.get("INPUT_START_TIMEOUT"))
    interval = int(os.environ.get("INPUT_INTERVAL"))
    cancel_jenkins_run_on_gh_cancel = bool(
        os.environ.get("INPUT_CANCEL_JENKINS_RUN_ON_GH_CANCEL")
    )

    run(
        url=url,
        job_name=job_name,
        username=username,
        api_token=api_token,
        parameters=parameters,
        cookies=cookies,
        wait=wait,
        timeout=timeout,
        start_timeout=start_timeout,
        interval=interval,
        cancel_jenkins_run_on_gh_cancel=cancel_jenkins_run_on_gh_cancel,
    )


if __name__ == "__main__":
    main()

import sys

sys.path.append("package")  # Assuming "package" is the parent directory of Werkzeug

from urllib.parse import unquote_plus
from werkzeug.utils import secure_filename
import boto3, json, os


def is_video_file(filename):
    video_extensions = [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"]
    file_extension = os.path.splitext(filename)[1]
    return file_extension.lower() in video_extensions


def handler(event, context):
    # print(json.dumps(event))
    sourceS3Bucket = event["Records"][0]["s3"]["bucket"]["name"]
    sourceS3Key = event["Records"][0]["s3"]["object"]["key"]
    sourceS3Key = unquote_plus(sourceS3Key)  # Unquote the key

    sourceS3 = f"s3://{sourceS3Bucket}/{sourceS3Key}"
    sourceS3Basename = os.path.splitext(os.path.basename(sourceS3))[0]
    print(f"sourceS3: {sourceS3}")

    folderName = os.path.dirname(sourceS3Key)
    file_name = os.path.basename(sourceS3Key)

    if not is_video_file(file_name):
        print(f"{file_name} is not a video file.")
        return {"statusCode": 200}

    fileNameWithoutExt = secure_filename(sourceS3Basename)

    ResourceId = fileNameWithoutExt  # Use the filename as the ResourceId
    print(f"ResourceId: {ResourceId}")

    destinationS3 = f"s3://{os.environ['DestinationBucket']}/{folderName}/{ResourceId}/"
    destinationS3basename = os.path.splitext(os.path.basename(destinationS3))[0]
    print(f"destinationS3: {destinationS3}")

    mediaConvertRole = os.environ["MediaConvertRole"]
    SpekeURL = os.environ["SpekeURL"]
    region = os.environ["AWS_DEFAULT_REGION"]
    statusCode = 200
    body = {}

    outputFileName = "manifest"

    # Use MediaConvert SDK UserMetadata to tag jobs with the ResourceId
    # Events from MediaConvert will have the ResourceId in UserMedata
    jobMetadata = {"ResourceId": ResourceId}

    try:
        # Job settings are in the lambda zip file in the current working directory
        with open("job.json") as json_data:
            jobSettings = json.load(json_data)

        # get the account-specific mediaconvert endpoint for this region
        mc_client = boto3.client("mediaconvert", region_name=region)
        endpoints = mc_client.describe_endpoints()

        # add the account-specific endpoint to the client session
        client = boto3.client(
            "mediaconvert",
            region_name=region,
            endpoint_url=endpoints["Endpoints"][0]["Url"],
            verify=True,
        )

        # Update the job settings with the source video from the S3 event and destination
        # paths for converted videos
        jobSettings["Inputs"][0]["FileInput"] = sourceS3

        ## MPEG DASH ISO output

        # Destination paths for converted videos
        S3KeyDASH = "dash/" + outputFileName

        # Configure output groups for each resolution
        jobSettings["OutputGroups"][0]["OutputGroupSettings"]["DashIsoGroupSettings"][
            "Destination"
        ] = (destinationS3 + S3KeyDASH)

        # Add the ResourceId to the SpekeKeyProvider in the DashIsoGroupSettings
        jobSettings["OutputGroups"][0]["OutputGroupSettings"]["DashIsoGroupSettings"][
            "Encryption"
        ]["SpekeKeyProvider"]["ResourceId"] = ResourceId

        # Add the AWS Speke URL to the SpekeKeyProvider in the DashIsoGroupSettings
        jobSettings["OutputGroups"][0]["OutputGroupSettings"]["DashIsoGroupSettings"][
            "Encryption"
        ]["SpekeKeyProvider"]["Url"] = SpekeURL

        ## APPLE HLS output

        # Destination paths for converted videos
        S3KeyHLS = "hls/" + outputFileName

        # Configure output groups for each resolution
        jobSettings["OutputGroups"][1]["OutputGroupSettings"]["HlsGroupSettings"][
            "Destination"
        ] = (destinationS3 + S3KeyHLS)

        # Add the ResourceId to the SpekeKeyProvider in the HlsGroupSettings
        jobSettings["OutputGroups"][1]["OutputGroupSettings"]["HlsGroupSettings"][
            "Encryption"
        ]["SpekeKeyProvider"]["ResourceId"] = ResourceId

        # Add the AWS Speke URL to the SpekeKeyProvider in the HlsGroupSettings
        jobSettings["OutputGroups"][1]["OutputGroupSettings"]["HlsGroupSettings"][
            "Encryption"
        ]["SpekeKeyProvider"]["Url"] = SpekeURL

        # Convert the video using AWS Elemental MediaConvert
        job = client.create_job(
            Role=mediaConvertRole,
            UserMetadata=jobMetadata,
            Settings=jobSettings,
        )
        # print(json.dumps(job, default=str))

    except Exception as e:
        print("Error:", str(e))

    finally:
        return {
            "statusCode": statusCode,
            "body": json.dumps(body),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }

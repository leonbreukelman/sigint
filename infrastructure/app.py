#!/usr/bin/env python3
"""
SIGINT Infrastructure - AWS CDK
"""
import aws_cdk as cdk
from constructs import Construct
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
)
import os


class SigintStack(Stack):
    """Main SIGINT infrastructure stack"""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # =================================================================
        # S3 Buckets
        # =================================================================
        
        # Data bucket (for JSON data)
        data_bucket = s3.Bucket(
            self, "DataBucket",
            bucket_name=f"sigint-data-{cdk.Aws.ACCOUNT_ID}",
            removal_policy=RemovalPolicy.RETAIN,
            cors=[s3.CorsRule(
                allowed_methods=[s3.HttpMethods.GET],
                allowed_origins=["*"],
                allowed_headers=["*"],
                max_age=3600
            )],
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="archive-cleanup",
                    prefix="archive/",
                    expiration=Duration.days(30)  # Keep 30 days of archives
                )
            ]
        )
        
        # Frontend bucket (for static website)
        frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            bucket_name=f"sigint-frontend-{cdk.Aws.ACCOUNT_ID}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            website_index_document="index.html",
            website_error_document="index.html",
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )
        
        # =================================================================
        # CloudFront Distribution
        # =================================================================
        
        # CloudFront Function to strip /data prefix from requests to data bucket
        strip_data_prefix_fn = cloudfront.Function(
            self, "StripDataPrefix",
            code=cloudfront.FunctionCode.from_inline("""
function handler(event) {
    var request = event.request;
    // Strip /data prefix from URI
    if (request.uri.startsWith('/data/')) {
        request.uri = request.uri.replace('/data', '');
    }
    return request;
}
"""),
            runtime=cloudfront.FunctionRuntime.JS_2_0,
        )
        
        # CloudFront distribution
        distribution = cloudfront.Distribution(
            self, "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(frontend_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/data/*": cloudfront.BehaviorOptions(
                    origin=origins.S3BucketOrigin.with_origin_access_control(data_bucket),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy(
                        self, "DataCachePolicy",
                        cache_policy_name="SigintDataCache",
                        default_ttl=Duration.seconds(30),
                        max_ttl=Duration.minutes(5),
                        min_ttl=Duration.seconds(0),
                        enable_accept_encoding_gzip=True,
                        enable_accept_encoding_brotli=True,
                    ),
                    origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                    function_associations=[
                        cloudfront.FunctionAssociation(
                            function=strip_data_prefix_fn,
                            event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                        )
                    ],
                )
            },
            default_root_object="index.html",
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,  # US, Canada, Europe only
        )
        
        # =================================================================
        # Lambda Layer (shared code)
        # =================================================================
        
        shared_layer = lambda_.LayerVersion(
            self, "SharedLayer",
            code=lambda_.Code.from_asset(
                "../lambdas/shared",
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output/python && cp -r . /asset-output/python/shared"
                    ]
                )
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="SIGINT shared modules"
        )
        
        # =================================================================
        # Lambda Functions
        # =================================================================
        
        # Common Lambda props
        lambda_env = {
            "DATA_BUCKET": data_bucket.bucket_name,
            "ANTHROPIC_API_KEY_SSM_PARAM": "/sigint/anthropic-api-key",  # Lambda fetches from SSM at runtime
            "POWERTOOLS_SERVICE_NAME": "sigint",
            "LOG_LEVEL": "INFO"
        }
        
        # Reporter Lambda (handles all categories via event parameter)
        reporter_fn = lambda_.Function(
            self, "ReporterFunction",
            function_name="sigint-reporter",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../lambdas/reporters"),
            layers=[shared_layer],
            environment=lambda_env,
            timeout=Duration.minutes(5),
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        data_bucket.grant_read_write(reporter_fn)
        # Grant SSM read permission for API key
        reporter_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:parameter/sigint/anthropic-api-key"]
        ))
        
        # Editor Lambda
        editor_fn = lambda_.Function(
            self, "EditorFunction",
            function_name="sigint-editor",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../lambdas/editor"),
            layers=[shared_layer],
            environment=lambda_env,
            timeout=Duration.minutes(3),
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        data_bucket.grant_read_write(editor_fn)
        # Grant SSM read permission for API key
        editor_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:parameter/sigint/anthropic-api-key"]
        ))
        
        # Narrative Tracker Lambda
        narrative_fn = lambda_.Function(
            self, "NarrativeFunction",
            function_name="sigint-narrative",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../lambdas/narrative"),
            layers=[shared_layer],
            environment=lambda_env,
            timeout=Duration.minutes(5),
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        data_bucket.grant_read_write(narrative_fn)
        # Grant SSM read permission for API key
        narrative_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:parameter/sigint/anthropic-api-key"]
        ))
        
        # =================================================================
        # EventBridge Schedules
        # =================================================================
        
        # Geopolitical - every 15 min
        events.Rule(
            self, "GeopoliticalSchedule",
            rule_name="sigint-geopolitical",
            schedule=events.Schedule.rate(Duration.minutes(15)),
            targets=[targets.LambdaFunction(
                reporter_fn,
                event=events.RuleTargetInput.from_object({"category": "geopolitical"})
            )]
        )
        
        # AI/ML - every 10 min
        events.Rule(
            self, "AiMlSchedule",
            rule_name="sigint-ai-ml",
            schedule=events.Schedule.rate(Duration.minutes(10)),
            targets=[targets.LambdaFunction(
                reporter_fn,
                event=events.RuleTargetInput.from_object({"category": "ai-ml"})
            )]
        )
        
        # Deep Tech - every 15 min
        events.Rule(
            self, "DeepTechSchedule",
            rule_name="sigint-deep-tech",
            schedule=events.Schedule.rate(Duration.minutes(15)),
            targets=[targets.LambdaFunction(
                reporter_fn,
                event=events.RuleTargetInput.from_object({"category": "deep-tech"})
            )]
        )
        
        # Crypto/Finance - every 5 min
        events.Rule(
            self, "CryptoFinanceSchedule",
            rule_name="sigint-crypto-finance",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            targets=[targets.LambdaFunction(
                reporter_fn,
                event=events.RuleTargetInput.from_object({"category": "crypto-finance"})
            )]
        )
        
        # Narrative Tracker - every 30 min
        events.Rule(
            self, "NarrativeSchedule",
            rule_name="sigint-narrative",
            schedule=events.Schedule.rate(Duration.minutes(30)),
            targets=[targets.LambdaFunction(narrative_fn)]
        )
        
        # Editor - every 5 min
        events.Rule(
            self, "EditorSchedule",
            rule_name="sigint-editor",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            targets=[targets.LambdaFunction(editor_fn)]
        )
        
        # =================================================================
        # Outputs
        # =================================================================
        
        CfnOutput(self, "DistributionUrl",
            value=f"https://{distribution.distribution_domain_name}",
            description="CloudFront distribution URL"
        )
        
        CfnOutput(self, "DataBucketName",
            value=data_bucket.bucket_name,
            description="Data bucket name"
        )
        
        CfnOutput(self, "FrontendBucketName",
            value=frontend_bucket.bucket_name,
            description="Frontend bucket name"
        )


# =================================================================
# App Entry Point
# =================================================================

app = cdk.App()

SigintStack(app, "SigintStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
    )
)

app.synth()

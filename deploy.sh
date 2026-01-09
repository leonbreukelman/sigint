#!/bin/bash
# SIGINT Deployment Script

set -e

echo "=========================================="
echo "SIGINT Deployment"
echo "=========================================="

# Check prerequisites
command -v aws >/dev/null 2>&1 || { echo "AWS CLI required but not installed."; exit 1; }
command -v cdk >/dev/null 2>&1 || { echo "AWS CDK required. Install with: npm install -g aws-cdk"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 required but not installed."; exit 1; }

# Get account info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo "Account: $ACCOUNT_ID"
echo "Region: $REGION"

# Check for Anthropic API key in SSM
echo ""
echo "Checking for Anthropic API key in SSM..."
if ! aws ssm get-parameter --name "/sigint/anthropic-api-key" --region $REGION >/dev/null 2>&1; then
    echo ""
    echo "ERROR: Anthropic API key not found in SSM Parameter Store."
    echo ""
    echo "Please create it with:"
    echo "  aws ssm put-parameter \\"
    echo "    --name '/sigint/anthropic-api-key' \\"
    echo "    --type 'SecureString' \\"
    echo "    --value 'YOUR_ANTHROPIC_API_KEY' \\"
    echo "    --region $REGION"
    echo ""
    exit 1
fi
echo "✓ API key found"

# Bootstrap CDK (if needed)
echo ""
echo "Bootstrapping CDK..."
cd infrastructure
cdk bootstrap aws://$ACCOUNT_ID/$REGION

# Install dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt -q

# Deploy
echo ""
echo "Deploying SIGINT stack..."
cdk deploy --require-approval never

# Get outputs
DISTRIBUTION_URL=$(aws cloudformation describe-stacks \
    --stack-name SigintStack \
    --query "Stacks[0].Outputs[?OutputKey=='DistributionUrl'].OutputValue" \
    --output text \
    --region $REGION)

FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name SigintStack \
    --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
    --output text \
    --region $REGION)

DATA_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name SigintStack \
    --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" \
    --output text \
    --region $REGION)

# Update frontend with data URL
echo ""
echo "Configuring frontend..."
cd ../frontend
# Inject the data URL into the HTML
DATA_URL="${DISTRIBUTION_URL}/data"
sed -i.bak "s|window.SIGINT_DATA_URL || '/data'|'${DATA_URL}'|g" app.js
rm -f app.js.bak

# Deploy frontend to S3
echo "Uploading frontend to S3..."
aws s3 sync . s3://$FRONTEND_BUCKET --delete --region $REGION

# Initialize data bucket with empty structures
echo ""
echo "Initializing data bucket..."
cd ..
cat > /tmp/empty-category.json << 'EOF'
{
  "category": "geopolitical",
  "items": [],
  "last_updated": "2024-01-01T00:00:00Z",
  "agent_notes": "Awaiting first run"
}
EOF

for category in geopolitical ai-ml deep-tech crypto-finance narrative breaking; do
    jq --arg cat "$category" '.category = $cat' /tmp/empty-category.json > /tmp/${category}.json
    aws s3 cp /tmp/${category}.json s3://$DATA_BUCKET/current/${category}.json --region $REGION
done

# Create empty dashboard
cat > /tmp/dashboard.json << 'EOF'
{
  "categories": {},
  "narratives": [],
  "last_updated": "2024-01-01T00:00:00Z",
  "system_status": "initializing"
}
EOF
aws s3 cp /tmp/dashboard.json s3://$DATA_BUCKET/current/dashboard.json --region $REGION

# Cleanup
rm -f /tmp/empty-category.json /tmp/*.json

# Invalidate CloudFront cache
echo ""
echo "Invalidating CloudFront cache..."
DIST_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Origins.Items[?DomainName=='${FRONTEND_BUCKET}.s3.amazonaws.com']].Id" \
    --output text)
if [ -n "$DIST_ID" ]; then
    aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*" >/dev/null
fi

echo ""
echo "=========================================="
echo "SIGINT Deployment Complete!"
echo "=========================================="
echo ""
echo "Dashboard URL: $DISTRIBUTION_URL"
echo ""
echo "Data Bucket: $DATA_BUCKET"
echo "Frontend Bucket: $FRONTEND_BUCKET"
echo ""
echo "The agents will start collecting data automatically."
echo "First data should appear within ~15 minutes."
echo ""

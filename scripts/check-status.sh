#!/bin/bash
# SIGINT Health Check Script
# Usage: ./scripts/check-status.sh

set -e

REGION=${AWS_DEFAULT_REGION:-us-east-1}
DATA_BUCKET="sigint-data-376849607951"

echo "========================================"
echo "SIGINT System Health Check"
echo "========================================"
echo ""

# Check Lambda function status
echo "📊 Lambda Function Status"
echo "----------------------------------------"
for fn in sigint-reporter sigint-editor sigint-narrative; do
    # Get last invocation time from logs
    LAST_EVENT=$(aws logs describe-log-streams \
        --log-group-name "/aws/lambda/$fn" \
        --order-by LastEventTime \
        --descending \
        --limit 1 \
        --query "logStreams[0].lastEventTimestamp" \
        --output text 2>/dev/null || echo "None")
    
    if [ "$LAST_EVENT" = "None" ] || [ -z "$LAST_EVENT" ]; then
        echo "  ❌ $fn: Never run"
    else
        # Convert timestamp to human readable
        LAST_RUN=$(date -d "@$((LAST_EVENT/1000))" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "Unknown")
        echo "  ✅ $fn: Last run at $LAST_RUN"
    fi
done

echo ""
echo "📁 Data Files Status"
echo "----------------------------------------"
aws s3 ls s3://$DATA_BUCKET/current/ 2>/dev/null | while read -r line; do
    SIZE=$(echo "$line" | awk '{print $3}')
    FILE=$(echo "$line" | awk '{print $4}')
    if [ "$SIZE" -lt 200 ]; then
        echo "  ⚠️  $FILE (${SIZE} bytes - possibly empty)"
    else
        echo "  ✅ $FILE (${SIZE} bytes)"
    fi
done

echo ""
echo "🔴 Recent Errors (last hour)"
echo "----------------------------------------"
ERROR_COUNT=0
for fn in sigint-reporter sigint-editor sigint-narrative; do
    ERRORS=$(aws logs filter-log-events \
        --log-group-name "/aws/lambda/$fn" \
        --start-time $(($(date +%s) * 1000 - 3600000)) \
        --filter-pattern "ERROR" \
        --query "events[].message" \
        --output text 2>/dev/null | head -5)
    
    if [ -n "$ERRORS" ]; then
        echo "  $fn:"
        echo "$ERRORS" | head -3 | sed 's/^/    /'
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
done

if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "  ✅ No errors in the last hour"
fi

echo ""
echo "📅 Scheduled Runs"
echo "----------------------------------------"
aws scheduler list-schedules --query "Schedules[?starts_with(Name, 'sigint')].{Name:Name,Schedule:ScheduleExpression,State:State}" --output table 2>/dev/null || echo "  Could not fetch schedules"

echo ""
echo "🌐 Dashboard URL"
echo "----------------------------------------"
DIST_URL=$(aws cloudformation describe-stacks \
    --stack-name SigintStack \
    --query "Stacks[0].Outputs[?OutputKey=='DistributionUrl'].OutputValue" \
    --output text 2>/dev/null)
echo "  $DIST_URL"
echo ""

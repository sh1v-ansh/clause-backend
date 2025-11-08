#!/bin/bash

echo "================================================================================"
echo "🧪 TESTING END-TO-END RAG ANALYSIS"
echo "================================================================================"
echo ""

# Step 1: Upload PDF
echo "📤 Step 1: Uploading sample-lease.pdf..."
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8000/upload \
  -F "file=@sample-lease.pdf")

FILE_ID=$(echo $UPLOAD_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['file_id'])")
echo "✅ Uploaded! File ID: $FILE_ID"
echo ""

# Step 2: Extract Metadata
echo "📋 Step 2: Extracting metadata..."
sleep 2
METADATA_RESPONSE=$(curl -s -X POST http://localhost:8000/extract-metadata \
  -H "Content-Type: application/json" \
  -d "{\"file_id\": \"$FILE_ID\"}")

echo "$METADATA_RESPONSE" | python3 -m json.tool > metadata_response.json
echo "Metadata response saved to: metadata_response.json"
echo ""

STATUS=$(echo $METADATA_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))")
echo "Status: $STATUS"
echo ""

# Check if metadata is complete or needs input
if [ "$STATUS" = "awaiting_metadata" ]; then
    echo "⚠️  Metadata incomplete - would show form to user"
    echo ""
    MISSING_FIELDS=$(echo $METADATA_RESPONSE | python3 -c "import sys, json; print(', '.join(json.load(sys.stdin).get('missing_fields', [])))")
    echo "Missing fields: $MISSING_FIELDS"
    echo ""
    echo "📝 Extracted metadata so far:"
    echo "$METADATA_RESPONSE" | python3 -c "import sys, json; import pprint; data = json.load(sys.stdin); pprint.pprint(data.get('metadata', {}))"
    echo ""
    echo "In the UI, user would fill in a form. For testing, let's submit complete metadata..."
    echo ""
    
    # Submit complete metadata
    echo "📝 Step 3: Submitting complete metadata..."
    SUBMIT_RESPONSE=$(curl -s -X POST http://localhost:8000/submit-metadata \
      -H "Content-Type: application/json" \
      -d "{
        \"file_id\": \"$FILE_ID\",
        \"metadata\": {
          \"documentType\": \"Commercial Lease Agreement\",
          \"parties\": {
            \"landlord\": \"Town of Swampscott\",
            \"tenant\": \"[REDACTED]\",
            \"property\": \"16 New Ocean Street, Swampscott, MA\"
          },
          \"leaseDetails\": {
            \"leaseType\": \"Commercial\",
            \"leaseTerm\": \"12 months with options\",
            \"monthlyRent\": \"Variable\",
            \"securityDeposit\": \"Not specified\"
          },
          \"pageCount\": 16
        }
      }")
    
    echo "✅ Metadata submitted!"
    echo "$SUBMIT_RESPONSE" | python3 -m json.tool
    echo ""
    
elif [ "$STATUS" = "metadata_complete" ]; then
    echo "✅ Metadata is complete! Starting analysis automatically..."
    echo ""
    
    # Start analysis
    ANALYZE_RESPONSE=$(curl -s -X POST http://localhost:8000/analyze \
      -H "Content-Type: application/json" \
      -d "{\"file_id\": \"$FILE_ID\"}")
    
    echo "$ANALYZE_RESPONSE" | python3 -m json.tool
    echo ""
fi

# Step 4: Poll for status
echo "⏳ Step 4: Waiting for analysis to complete..."
echo "This will take 2-5 minutes depending on document size..."
echo ""

ATTEMPTS=0
MAX_ATTEMPTS=60  # 5 minutes (60 * 5 seconds)

while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    sleep 5
    STATUS_RESPONSE=$(curl -s http://localhost:8000/status/$FILE_ID)
    CURRENT_STATUS=$(echo $STATUS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))")
    PROGRESS=$(echo $STATUS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', 0))")
    MESSAGE=$(echo $STATUS_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('message', ''))")
    
    echo "[$PROGRESS%] $MESSAGE"
    
    if [ "$CURRENT_STATUS" = "completed" ]; then
        echo ""
        echo "✅ Analysis completed!"
        break
    elif [ "$CURRENT_STATUS" = "failed" ]; then
        echo ""
        echo "❌ Analysis failed!"
        echo "$STATUS_RESPONSE" | python3 -m json.tool
        exit 1
    fi
    
    ATTEMPTS=$((ATTEMPTS + 1))
done

if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
    echo ""
    echo "⏱️  Timeout waiting for analysis"
    exit 1
fi

# Step 5: Get results
echo ""
echo "📊 Step 5: Retrieving analysis results..."
RESULTS=$(curl -s http://localhost:8000/document/$FILE_ID)
echo "$RESULTS" | python3 -m json.tool > final_analysis.json
echo "✅ Results saved to: final_analysis.json"
echo ""

# Display summary
echo "================================================================================"
echo "📈 ANALYSIS SUMMARY"
echo "================================================================================"
echo "$RESULTS" | python3 << 'PYTHON'
import sys, json
data = json.load(sys.stdin)
analysis = data.get('analysis', {})

print(f"Document ID: {analysis.get('documentId', 'N/A')}")
print(f"Status: {analysis.get('analysisSummary', {}).get('status', 'N/A')}")
print(f"Overall Risk: {analysis.get('analysisSummary', {}).get('overallRisk', 'N/A')}")
print(f"Issues Found: {analysis.get('analysisSummary', {}).get('issuesFound', 0)}")
print(f"Estimated Recovery: {analysis.get('analysisSummary', {}).get('estimatedRecovery', '$0')}")
print()

highlights = analysis.get('highlights', [])
print(f"Total Highlights: {len(highlights)}")

red = len([h for h in highlights if h.get('color') == 'red'])
orange = len([h for h in highlights if h.get('color') == 'orange'])
yellow = len([h for h in highlights if h.get('color') == 'yellow'])
green = len([h for h in highlights if h.get('color') == 'green'])

print(f"  🔴 Red (Illegal): {red}")
print(f"  🟠 Orange (High Risk): {orange}")
print(f"  🟡 Yellow (Medium Risk): {yellow}")
print(f"  🟢 Green (Favorable): {green}")
print()

if highlights:
    print("Sample Highlights:")
    for i, h in enumerate(highlights[:3], 1):
        print(f"\n{i}. [{h.get('color').upper()}] {h.get('category', 'Unknown')}")
        print(f"   Page: {h.get('pageNumber')}")
        print(f"   Text: {h.get('text', '')[:100]}...")
        rect = h.get('position', {}).get('boundingRect', {})
        print(f"   Coords: ({rect.get('x1')}, {rect.get('y1')}) to ({rect.get('x2')}, {rect.get('y2')})")
PYTHON

echo ""
echo "================================================================================"
echo "✅ END-TO-END TEST COMPLETE!"
echo "================================================================================"
echo ""
echo "Files created:"
echo "  - metadata_response.json (metadata extraction result)"
echo "  - final_analysis.json (complete analysis with highlights)"
echo ""
echo "To view frontend: http://localhost:8000/app"
echo ""


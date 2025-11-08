"""
End-to-end test of the two-stage RAG analysis workflow
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add scripts directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))

from pdf_extraction import PDFExtractor
from document_chunker import DocumentChunker
from rag_analyzer import RAGAnalyzer


def test_full_workflow(pdf_path: str, output_path: str = None):
    """
    Test complete two-stage workflow
    
    Args:
        pdf_path: Path to PDF file to analyze
        output_path: Path to save output JSON (optional)
    """
    print("=" * 80)
    print("TWO-STAGE RAG ANALYSIS WORKFLOW TEST")
    print("=" * 80)
    
    # Validate PDF exists
    if not os.path.exists(pdf_path):
        print(f"❌ Error: PDF file not found: {pdf_path}")
        return
    
    print(f"\n📄 Testing with: {pdf_path}")
    print(f"   File size: {os.path.getsize(pdf_path) // 1024} KB")
    
    try:
        # Initialize components
        print("\n🔧 Initializing components...")
        extractor = PDFExtractor()
        chunker = DocumentChunker()
        analyzer = RAGAnalyzer()
        
        # Stage 1: Extract text
        print("\n" + "=" * 80)
        print("STAGE 1: METADATA EXTRACTION")
        print("=" * 80)
        
        print("\n📖 Extracting text from PDF...")
        lease_text = extractor.extract_text(pdf_path)
        print(f"   ✅ Extracted {len(lease_text)} characters")
        
        # Extract metadata
        print("\n📋 Extracting document metadata with Gemini...")
        metadata = analyzer.extract_metadata(lease_text, pdf_path)
        
        print("\n✅ Metadata extraction complete!")
        print("\nExtracted Metadata:")
        print(f"   File Name: {metadata.get('fileName')}")
        print(f"   Document Type: {metadata.get('documentType')}")
        print(f"   Landlord: {metadata.get('parties', {}).get('landlord')}")
        print(f"   Tenant: {metadata.get('parties', {}).get('tenant')}")
        print(f"   Property: {metadata.get('parties', {}).get('property')}")
        print(f"   Lease Type: {metadata.get('leaseDetails', {}).get('leaseType')}")
        print(f"   Term: {metadata.get('leaseDetails', {}).get('leaseTerm')}")
        print(f"   Rent: {metadata.get('leaseDetails', {}).get('monthlyRent')}")
        
        # Stage 2: Full Analysis
        print("\n" + "=" * 80)
        print("STAGE 2: FULL RAG ANALYSIS")
        print("=" * 80)
        
        print("\n📝 Chunking document...")
        lease_chunks = chunker.chunk_document(lease_text, max_tokens=4000)
        print(f"   ✅ Created {len(lease_chunks)} chunks")
        
        print("\n🔍 Analyzing chunks against MA laws...")
        chunk_analyses = []
        for i, chunk in enumerate(lease_chunks):
            print(f"   Analyzing chunk {i+1}/{len(lease_chunks)}...", end='\r')
            
            # Search for relevant laws
            relevant_laws = analyzer.search_relevant_laws(chunk['text'], top_k=8)
            
            # Analyze chunk
            analysis = analyzer.analyze_chunk(chunk, relevant_laws)
            chunk_analyses.append(analysis)
            
            # Print summary
            illegal_count = len(analysis.get('illegal_clauses', []))
            risky_count = len(analysis.get('risky_terms', []))
            if illegal_count > 0 or risky_count > 0:
                print(f"   Chunk {i+1}/{len(lease_chunks)}: Found {illegal_count} illegal, {risky_count} risky")
        
        print(f"\n   ✅ Analysis complete for all {len(lease_chunks)} chunks")
        
        # Consolidate results
        print("\n📊 Consolidating analysis with PDF coordinates...")
        
        # Create mock PII summary
        pii_summary = {
            "total_redactions": 0,
            "redaction_details": []
        }
        
        # Generate file ID
        file_id = "test-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        
        # Consolidate with complete structure
        final_analysis = analyzer.consolidate_analysis(
            chunk_analyses,
            lease_text,
            metadata,
            pii_summary,
            file_id,
            pdf_path
        )
        
        # Close analyzer
        analyzer.close()
        
        # Print summary
        print("\n" + "=" * 80)
        print("ANALYSIS RESULTS SUMMARY")
        print("=" * 80)
        
        summary = final_analysis.get('analysisSummary', {})
        print(f"\n📈 Overall Risk: {summary.get('overallRisk', 'Unknown')}")
        print(f"   Issues Found: {summary.get('issuesFound', 0)}")
        print(f"   Potential Recovery: {summary.get('estimatedRecovery', '$0')}")
        print(f"   Highlights: {len(final_analysis.get('highlights', []))}")
        
        # Count by color
        highlights = final_analysis.get('highlights', [])
        red_count = len([h for h in highlights if h['color'] == 'red'])
        orange_count = len([h for h in highlights if h['color'] == 'orange'])
        yellow_count = len([h for h in highlights if h['color'] == 'yellow'])
        green_count = len([h for h in highlights if h['color'] == 'green'])
        
        print(f"\n   🔴 Red (Illegal): {red_count}")
        print(f"   🟠 Orange (High Risk): {orange_count}")
        print(f"   🟡 Yellow (Medium Risk): {yellow_count}")
        print(f"   🟢 Green (Favorable): {green_count}")
        
        # Show top issues
        if summary.get('topIssues'):
            print("\n   Top Issues:")
            for i, issue in enumerate(summary['topIssues'][:3], 1):
                print(f"   {i}. {issue['title']} - {issue['severity']} ({issue['amount']})")
        
        # Save output
        if not output_path:
            # Default output path
            pdf_name = Path(pdf_path).stem
            output_path = f"{pdf_name}_analysis_output.json"
        
        print(f"\n💾 Saving analysis to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_analysis, f, indent=2, ensure_ascii=False)
        
        print(f"   ✅ Saved {os.path.getsize(output_path) // 1024} KB")
        
        # Validate JSON structure
        print("\n✅ Validating JSON structure...")
        required_keys = [
            'documentId', 'pdfUrl', 'documentMetadata', 
            'deidentificationSummary', 'keyDetailsDetected', 
            'analysisSummary', 'highlights'
        ]
        
        missing_keys = [key for key in required_keys if key not in final_analysis]
        if missing_keys:
            print(f"   ⚠️  Missing keys: {missing_keys}")
        else:
            print("   ✅ All required keys present")
        
        # Validate highlights structure
        if highlights:
            sample_highlight = highlights[0]
            highlight_keys = ['id', 'pageNumber', 'color', 'priority', 'category', 
                            'text', 'statute', 'explanation', 'damages_estimate', 'position']
            missing_highlight_keys = [key for key in highlight_keys if key not in sample_highlight]
            if missing_highlight_keys:
                print(f"   ⚠️  Missing highlight keys: {missing_highlight_keys}")
            else:
                print("   ✅ Highlight structure valid")
            
            # Check position structure
            position = sample_highlight.get('position', {})
            if 'boundingRect' in position and 'rects' in position:
                print("   ✅ Position coordinates present")
            else:
                print("   ⚠️  Position coordinates missing")
        
        print("\n" + "=" * 80)
        print("✅ TEST COMPLETE - Analysis saved successfully!")
        print("=" * 80)
        print(f"\nOutput file: {output_path}")
        print(f"View with: cat {output_path} | python -m json.tool")
        
        return final_analysis
        
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Default to sample-lease.pdf
    pdf_file = "sample-lease.pdf"
    output_file = "sample-lease_final_analysis.json"
    
    # Check if custom PDF path provided
    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
    
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    
    # Run test
    result = test_full_workflow(pdf_file, output_file)
    
    if result:
        print("\n✅ Success! Analysis complete.")
        sys.exit(0)
    else:
        print("\n❌ Test failed.")
        sys.exit(1)


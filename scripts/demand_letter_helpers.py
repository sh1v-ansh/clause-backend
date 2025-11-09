"""
Helper functions for demand letter generation
"""
import sys
import os

# Add scripts directory to path
sys.path.append(os.path.dirname(__file__))


def format_issues_for_prompt(highlights):
    """Convert highlights array into formatted text for prompt - optimized for token efficiency"""
    formatted = []
    for i, highlight in enumerate(highlights, 1):
        # Truncate fields to reduce tokens - keep essential info only
        category = highlight.get('category', '')[:60]  # Limit to 60 chars
        statute = highlight.get('statute', '')[:50]     # Limit to 50 chars
        text = highlight.get('text', '')[:150]          # Limit to 150 chars
        explanation = highlight.get('explanation', '')[:200]  # Limit to 200 chars
        damages = highlight.get('damages_estimate', 0) or 0
        
        # Compact format - one line per issue to save tokens
        issue_text = f"{i}. {category} | {statute} | ${damages:,.0f} | {text[:100]}"
        formatted.append(issue_text)
    return "\n".join(formatted)  # Single newline instead of separator


def build_user_prompt(user_prompt, analysis_json, sender, recipient, preferences):
    """Build the complete prompt for Gemini API"""
    
    # Extract highlights from analysis_json - prioritize issues with damages
    all_highlights = analysis_json.get('highlights', [])
    highlights_with_damages = [
        h for h in all_highlights 
        if h.get('damages_estimate', 0) and h.get('damages_estimate', 0) > 0
    ]
    # Use highlights with damages, or all highlights if none have damages
    highlights = highlights_with_damages if highlights_with_damages else all_highlights
    
    issues_text = format_issues_for_prompt(highlights) if highlights else "No issues found."
    
    # Calculate total damages
    total_damages = sum(
        (h.get('damages_estimate', 0) or 0) 
        for h in highlights
    )
    
    # Get document metadata
    document_metadata = analysis_json.get('documentMetadata', {})
    document_title = document_metadata.get('fileName', 'Lease Agreement')
    analysis_date = analysis_json.get('document_info', {}).get('analysis_date', 'Unknown')
    if not analysis_date or analysis_date == 'Unknown':
        from datetime import datetime
        analysis_date = datetime.now().strftime('%Y-%m-%d')
    
    # Get key details
    key_details = analysis_json.get('keyDetailsDetected', {})
    property_address = key_details.get('propertyAddress', recipient.get('address', ''))
    monthly_rent = key_details.get('monthlyRent', 'Not specified')
    security_deposit = key_details.get('securityDeposit', 'Not specified')
    lease_term = key_details.get('leaseTerm', 'Not specified')
    
    # Get analysis summary
    analysis_summary = analysis_json.get('analysisSummary', {})
    overall_risk = analysis_summary.get('overallRisk', 'Unknown')
    issues_found = analysis_summary.get('issuesFound', len(highlights))
    
    contact_person = recipient.get('contact_person', '')
    contact_line = f"{contact_person}\n" if contact_person else ""
    
    # Build optimized, concise prompt to reduce token usage
    # Truncate long fields to save tokens
    doc_title_short = document_title[:50] if document_title else "Lease Agreement"
    property_addr_short = property_address[:80] if property_address else "Property"
    
    prompt = f"""Generate a professional demand letter in PLAIN TEXT.

SENDER: {sender.get('name', '[YOUR NAME]')}, {sender.get('address', '[YOUR ADDRESS]')}, {sender.get('city', '[CITY]')} {sender.get('state', 'MA')} {sender.get('zip', '[ZIP]')}
RECIPIENT: {recipient.get('name', '[LANDLORD NAME]')}, {recipient.get('address', '[LANDLORD ADDRESS]')}, {recipient.get('city', '[CITY]')} {recipient.get('state', 'MA')} {recipient.get('zip', '[ZIP]')}

LEASE: {doc_title_short} | {property_addr_short} | Rent: {monthly_rent} | Deposit: {security_deposit}
ISSUES: {issues_found} violations | Total: ${total_damages:,.0f} | Risk: {overall_risk}

VIOLATIONS:
{issues_text}

REQUIREMENTS:
- Plain text (NO LaTeX, NO markdown)
- Tone: {preferences.get('tone', 'firm')}
- Deadline: {preferences.get('deadline_days', 30)} days
- Include: violations with citations (M.G.L. c. 186 §15B), damages breakdown, total ${total_damages:,.0f}, deadline, consequences
- Placeholders: [YOUR NAME], [YOUR ADDRESS], [LANDLORD NAME], [LANDLORD ADDRESS], [DATE]
- Structure: sender address, date, recipient address, RE line, salutation, body, closing, signature
- Massachusetts law only - verify citations
- Professional format, ready to copy/paste

Generate the letter now."""
    return prompt


def validate_latex(latex_source):
    """Validate that generated content is valid LaTeX - lenient validation"""
    if not latex_source:
        return False
    
    # Remove markdown code fences if present
    latex_source_clean = latex_source.strip()
    if latex_source_clean.startswith('```'):
        lines = latex_source_clean.split('\n')
        latex_source_clean = '\n'.join(lines[1:-1]) if len(lines) > 2 else latex_source_clean
        latex_source_clean = latex_source_clean.strip()
    
    # More lenient validation - just check if it has substantial content
    # Don't require exact LaTeX format since user might want plain text
    checks = [
        len(latex_source_clean) > 200,  # Should be substantial content
    ]
    
    # Optional: check for LaTeX if it looks like LaTeX
    has_latex = '\\documentclass' in latex_source_clean or 'documentclass' in latex_source_clean.lower()
    
    # If it has LaTeX markers, validate them
    if has_latex:
        checks.append('\\documentclass' in latex_source_clean or 'documentclass' in latex_source_clean.lower())
        # Don't require \end{document} - user can add it
    
    return all(checks)


def clean_latex_output(latex_source):
    """Remove any markdown formatting from LaTeX output"""
    # Remove markdown code fences
    if latex_source.startswith('```'):
        # Remove opening fence
        lines = latex_source.split('\n')
        start_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('```'):
                start_idx = i + 1
                break
        latex_source = '\n'.join(lines[start_idx:])
    
    if latex_source.endswith('```'):
        # Remove closing fence
        lines = latex_source.split('\n')
        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip().startswith('```'):
                end_idx = i
                break
        latex_source = '\n'.join(lines[:end_idx])
    
    # Remove any remaining markdown artifacts
    latex_source = latex_source.replace('```latex', '').replace('```', '')
    
    # Remove any leading/trailing whitespace
    latex_source = latex_source.strip()
    
    return latex_source


def generate_default_sender_recipient(analysis_json):
    """Generate default sender and recipient from analysis data"""
    key_details = analysis_json.get('keyDetailsDetected', {})
    document_metadata = analysis_json.get('documentMetadata', {})
    parties = document_metadata.get('parties', {})
    
    # Get tenant name (sender)
    tenant_name = key_details.get('tenant') or parties.get('tenant') or '[YOUR NAME]'
    property_address = key_details.get('propertyAddress') or parties.get('property') or '[PROPERTY ADDRESS]'
    
    # Get landlord name (recipient)
    landlord_name = key_details.get('landlord') or parties.get('landlord') or '[LANDLORD NAME]'
    
    # Parse property address to extract city, state, zip if possible
    address_parts = property_address.split(',') if property_address else []
    city = address_parts[-2].strip() if len(address_parts) >= 2 else '[CITY]'
    state_zip = address_parts[-1].strip() if len(address_parts) >= 1 else 'MA [ZIP]'
    state = 'MA'
    zip_code = '[ZIP CODE]'
    
    # Try to extract state and zip
    state_zip_parts = state_zip.split()
    if len(state_zip_parts) >= 2:
        state = state_zip_parts[0]
        zip_code = state_zip_parts[-1]
    elif len(state_zip_parts) == 1:
        if state_zip_parts[0].isdigit():
            zip_code = state_zip_parts[0]
        else:
            state = state_zip_parts[0]
    
    sender = {
        'name': tenant_name,
        'address': '[YOUR ADDRESS]',
        'city': city if city != '[CITY]' else '[YOUR CITY]',
        'state': state,
        'zip': zip_code if zip_code != '[ZIP CODE]' else '[YOUR ZIP CODE]',
        'phone': '[YOUR PHONE]',
        'email': '[YOUR EMAIL]'
    }
    
    recipient = {
        'name': landlord_name,
        'address': '[LANDLORD ADDRESS]',
        'city': city if city != '[CITY]' else '[LANDLORD CITY]',
        'state': state,
        'zip': zip_code if zip_code != '[ZIP CODE]' else '[LANDLORD ZIP CODE]',
        'contact_person': None
    }
    
    return sender, recipient


def validate_request_data(data):
    """Validate that all required fields are present - lenient validation"""
    # Only require analysis_json
    if 'analysis_json' not in data:
        return "Missing required field: analysis_json"
    
    # Validate analysis_json
    analysis_json = data.get('analysis_json', {})
    if 'highlights' not in analysis_json:
        return "Missing highlights in analysis_json"
    
    highlights = analysis_json.get('highlights', [])
    if not isinstance(highlights, list):
        return "highlights must be an array"
    
    if len(highlights) == 0:
        return "highlights array cannot be empty"
    
    # Generate defaults if sender/recipient not provided or incomplete
    # Check if sender is missing or empty dict
    sender_provided = 'sender' in data and data.get('sender') and isinstance(data.get('sender'), dict) and len(data.get('sender', {})) > 0
    recipient_provided = 'recipient' in data and data.get('recipient') and isinstance(data.get('recipient'), dict) and len(data.get('recipient', {})) > 0
    
    if not sender_provided or not recipient_provided:
        sender_default, recipient_default = generate_default_sender_recipient(analysis_json)
        
        if not sender_provided:
            data['sender'] = sender_default
            print(f"   [DEFAULT] Generated sender: {sender_default.get('name', 'N/A')}")
        
        if not recipient_provided:
            data['recipient'] = recipient_default
            print(f"   [DEFAULT] Generated recipient: {recipient_default.get('name', 'N/A')}")
    
    # Ensure sender exists and has required fields
    if 'sender' not in data:
        sender_default, _ = generate_default_sender_recipient(analysis_json)
        data['sender'] = sender_default
    
    # Ensure recipient exists and has required fields
    if 'recipient' not in data:
        _, recipient_default = generate_default_sender_recipient(analysis_json)
        data['recipient'] = recipient_default
    
    # Ensure required fields exist with defaults
    sender = data.get('sender', {})
    recipient = data.get('recipient', {})
    
    # Fill in missing sender fields with placeholders
    if not sender.get('address'):
        sender['address'] = '[YOUR ADDRESS]'
    if not sender.get('city'):
        sender['city'] = '[YOUR CITY]'
    if not sender.get('state'):
        sender['state'] = 'MA'
    if not sender.get('zip'):
        sender['zip'] = '[YOUR ZIP CODE]'
    
    # Fill in missing recipient fields with placeholders
    if not recipient.get('address'):
        recipient['address'] = '[LANDLORD ADDRESS]'
    if not recipient.get('city'):
        recipient['city'] = '[LANDLORD CITY]'
    if not recipient.get('state'):
        recipient['state'] = 'MA'
    if not recipient.get('zip'):
        recipient['zip'] = '[LANDLORD ZIP CODE]'
    
    # Set default prompt if not provided
    if not data.get('prompt'):
        total_damages = sum((h.get('damages_estimate', 0) or 0) for h in highlights)
        data['prompt'] = f"Generate a professional demand letter requesting ${total_damages:,} in damages resulting from violations of Massachusetts housing law found in the lease agreement."
    
    # Set default preferences if not provided
    if 'preferences' not in data:
        data['preferences'] = {'deadline_days': 30, 'tone': 'firm'}
    
    return None


"""
PII Redaction Module
Detects and redacts personally identifiable information from documents
"""
import re
import json
from typing import Dict, Tuple, List
from pathlib import Path
from cryptography.fernet import Fernet
import PyPDF2

try:
    import spacy
    SPACY_AVAILABLE = True
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("⚠️  spaCy model not found. Run: python -m spacy download en_core_web_sm")
        SPACY_AVAILABLE = False
except ImportError:
    print("⚠️  spaCy not installed. Run: pip install spacy")
    SPACY_AVAILABLE = False


class PIIRedactor:
    """Detect and redact PII from text"""
    
    # Regex patterns for PII detection
    PATTERNS = {
        'ssn': [
            r'\b\d{3}-\d{2}-\d{4}\b',  # 123-45-6789
            r'\b\d{3}\s\d{2}\s\d{4}\b',  # 123 45 6789
            r'\b\d{9}\b'  # 123456789 (standalone)
        ],
        'phone': [
            r'\b\d{3}-\d{3}-\d{4}\b',  # 123-456-7890
            r'\b\(\d{3}\)\s?\d{3}-\d{4}\b',  # (123) 456-7890 or (123)456-7890
            r'\b\d{3}\.\d{3}\.\d{4}\b',  # 123.456.7890
            r'\b\d{10}\b',  # 1234567890 (standalone)
            r'\+1\s?\d{3}\s?\d{3}\s?\d{4}\b'  # +1 123 456 7890
        ],
        'email': [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        ],
        'date_of_birth': [
            r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12][0-9]|3[01])[/-](?:19|20)\d{2}\b',  # MM/DD/YYYY
            r'\b(?:19|20)\d{2}[/-](?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12][0-9]|3[01])\b',  # YYYY/MM/DD
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+(?:19|20)\d{2}\b'  # Month DD, YYYY
        ],
        'address': [
            # Street address pattern: number + street name + street type
            r'\b\d+\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Way|Place|Pl)\b',
            # PO Box
            r'\bP\.?\s?O\.?\s+Box\s+\d+\b'
        ],
        'zip_code': [
            r'\b\d{5}(?:-\d{4})?\b'  # 12345 or 12345-6789
        ],
        'credit_card': [
            r'\b(?:\d{4}[\s-]?){3}\d{4}\b'  # 1234 5678 9012 3456 or 1234-5678-9012-3456
        ],
        'license_plate': [
            r'\b[A-Z]{2,3}\s?\d{3,4}\b'  # ABC 1234 or ABC1234 (letters then numbers)
        ]
    }
    
    def __init__(self, use_spacy: bool = True):
        """
        Initialize PII Redactor
        
        Args:
            use_spacy: Whether to use spaCy for named entity recognition
        """
        self.use_spacy = use_spacy and SPACY_AVAILABLE
        self.pii_mapping = {}
        self.redaction_count = {key: 0 for key in self.PATTERNS.keys()}
        if self.use_spacy:
            self.redaction_count['person_name'] = 0
            self.redaction_count['organization'] = 0
    
    def detect_and_redact(self, text: str) -> Tuple[str, Dict[str, List[str]]]:
        """
        Detect and redact PII from text
        
        Args:
            text: Original text
            
        Returns:
            Tuple of (redacted_text, pii_mapping)
        """
        redacted_text = text
        pii_found = {key: [] for key in self.PATTERNS.keys()}
        
        # Apply regex patterns
        for pii_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, redacted_text, re.IGNORECASE)
                for match in matches:
                    original = match.group(0)
                    
                    # Skip if looks like year only (for dates)
                    if pii_type == 'date_of_birth' and len(original) == 4 and original.isdigit():
                        continue
                    
                    # Skip common false positives
                    if self._is_false_positive(original, pii_type):
                        continue
                    
                    token = self._get_redaction_token(pii_type)
                    redacted_text = redacted_text.replace(original, token, 1)
                    pii_found[pii_type].append(original)
                    self.redaction_count[pii_type] += 1
        
        # Use spaCy for named entity recognition
        if self.use_spacy:
            person_entities, org_entities = self._detect_named_entities(text)
            
            # Redact person names
            for entity in person_entities:
                if entity in redacted_text:  # Only redact if still present
                    token = "[NAME_REDACTED]"
                    redacted_text = redacted_text.replace(entity, token)
                    if 'person_name' not in pii_found:
                        pii_found['person_name'] = []
                    pii_found['person_name'].append(entity)
                    self.redaction_count['person_name'] += 1
            
            # Redact organization names (optional - may want to keep some)
            for entity in org_entities:
                # Skip common legal terms
                if entity.lower() in ['landlord', 'tenant', 'lessor', 'lessee']:
                    continue
                if entity in redacted_text:
                    token = "[ORG_REDACTED]"
                    redacted_text = redacted_text.replace(entity, token)
                    if 'organization' not in pii_found:
                        pii_found['organization'] = []
                    pii_found['organization'].append(entity)
                    self.redaction_count['organization'] += 1
        
        self.pii_mapping = pii_found
        return redacted_text, pii_found
    
    def _is_false_positive(self, text: str, pii_type: str) -> bool:
        """Check if detected PII is likely a false positive"""
        
        # For phone numbers, skip if it's part of a common pattern
        if pii_type == 'phone':
            # Skip numbers like 1234567890 that might be IDs
            if text.isdigit() and len(text) == 10:
                # Could be phone, but also could be other ID
                # For now, we'll keep these redacted for safety
                pass
        
        # For ZIP codes, skip if it looks like a year
        if pii_type == 'zip_code':
            if text.isdigit() and 1900 <= int(text) <= 2100:
                return True
        
        # For addresses, skip if it's a section reference
        if pii_type == 'address':
            if 'section' in text.lower() or 'chapter' in text.lower():
                return True
        
        return False
    
    def _detect_named_entities(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Use spaCy to detect named entities
        
        Returns:
            Tuple of (person_names, organizations)
        """
        if not self.use_spacy:
            return [], []
        
        # Process text in chunks to avoid memory issues
        max_length = 1000000  # spaCy's default max length
        if len(text) > max_length:
            # Process in chunks
            chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]
            all_persons = []
            all_orgs = []
            for chunk in chunks:
                doc = nlp(chunk)
                persons = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
                orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
                all_persons.extend(persons)
                all_orgs.extend(orgs)
            return list(set(all_persons)), list(set(all_orgs))
        else:
            doc = nlp(text)
            persons = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
            orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
            return list(set(persons)), list(set(orgs))
    
    def _get_redaction_token(self, pii_type: str) -> str:
        """Get redaction token for PII type"""
        tokens = {
            'ssn': '[SSN_REDACTED]',
            'phone': '[PHONE_REDACTED]',
            'email': '[EMAIL_REDACTED]',
            'date_of_birth': '[DOB_REDACTED]',
            'address': '[ADDRESS_REDACTED]',
            'zip_code': '[ZIP_REDACTED]',
            'credit_card': '[CARD_REDACTED]',
            'license_plate': '[PLATE_REDACTED]'
        }
        return tokens.get(pii_type, '[REDACTED]')
    
    def get_redaction_summary(self) -> Dict[str, int]:
        """Get summary of redactions performed"""
        return {k: v for k, v in self.redaction_count.items() if v > 0}


class PIIEncryption:
    """Encrypt and decrypt PII mappings"""
    
    def __init__(self, key_file: Path = None):
        """
        Initialize encryption handler
        
        Args:
            key_file: Path to file containing encryption key
        """
        self.key_file = key_file or Path("data/encryption_keys.json")
        self.key_file.parent.mkdir(exist_ok=True)
        self.keys = self._load_keys()
    
    def _load_keys(self) -> Dict[str, str]:
        """Load encryption keys from file"""
        if self.key_file.exists():
            with open(self.key_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_keys(self):
        """Save encryption keys to file"""
        with open(self.key_file, 'w') as f:
            json.dump(self.keys, f, indent=2)
    
    def generate_key(self, file_id: str) -> str:
        """Generate and store encryption key for file"""
        key = Fernet.generate_key().decode()
        self.keys[file_id] = key
        self._save_keys()
        return key
    
    def encrypt_pii_mapping(self, file_id: str, pii_mapping: Dict) -> str:
        """
        Encrypt PII mapping
        
        Args:
            file_id: Document identifier
            pii_mapping: Dictionary of PII found
            
        Returns:
            Encrypted JSON string
        """
        # Get or generate key
        if file_id not in self.keys:
            self.generate_key(file_id)
        
        key = self.keys[file_id]
        fernet = Fernet(key.encode())
        
        # Serialize and encrypt
        json_data = json.dumps(pii_mapping).encode()
        encrypted_data = fernet.encrypt(json_data)
        
        return encrypted_data.decode()
    
    def decrypt_pii_mapping(self, file_id: str, encrypted_data: str) -> Dict:
        """
        Decrypt PII mapping
        
        Args:
            file_id: Document identifier
            encrypted_data: Encrypted JSON string
            
        Returns:
            Decrypted PII mapping
        """
        if file_id not in self.keys:
            raise ValueError(f"No encryption key found for file_id: {file_id}")
        
        key = self.keys[file_id]
        fernet = Fernet(key.encode())
        
        # Decrypt and deserialize
        decrypted_data = fernet.decrypt(encrypted_data.encode())
        pii_mapping = json.loads(decrypted_data.decode())
        
        return pii_mapping
    
    def delete_key(self, file_id: str):
        """Delete encryption key for file"""
        if file_id in self.keys:
            del self.keys[file_id]
            self._save_keys()


def redact_pdf(pdf_path: str, use_spacy: bool = True) -> Tuple[str, Dict, Dict]:
    """
    Extract text from PDF and redact PII
    
    Args:
        pdf_path: Path to PDF file
        use_spacy: Whether to use spaCy NER
        
    Returns:
        Tuple of (redacted_text, pii_mapping, redaction_summary)
    """
    # Extract text from PDF
    text = ""
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n\n"
    
    # Redact PII
    redactor = PIIRedactor(use_spacy=use_spacy)
    redacted_text, pii_mapping = redactor.detect_and_redact(text)
    summary = redactor.get_redaction_summary()
    
    return redacted_text, pii_mapping, summary


def save_redacted_mapping(file_id: str, pii_mapping: Dict, encryption: PIIEncryption) -> str:
    """
    Save encrypted PII mapping for a file
    
    Args:
        file_id: Document identifier
        pii_mapping: PII that was redacted
        encryption: PIIEncryption instance
        
    Returns:
        Encrypted mapping string
    """
    encrypted = encryption.encrypt_pii_mapping(file_id, pii_mapping)
    
    # Save to file
    mapping_file = Path(f"data/pii_mappings/{file_id}.enc")
    mapping_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(mapping_file, 'w') as f:
        f.write(encrypted)
    
    return encrypted


if __name__ == "__main__":
    # Test the redaction
    test_text = """
    John Smith lives at 123 Main Street, Boston, MA 02101.
    His SSN is 123-45-6789 and phone is (617) 555-1234.
    Email: john.smith@email.com
    DOB: 01/15/1980
    
    Landlord: ABC Properties LLC
    Tenant: Jane Doe
    """
    
    print("Testing PII Redaction...")
    print("="*80)
    
    redactor = PIIRedactor(use_spacy=SPACY_AVAILABLE)
    redacted, pii_found = redactor.detect_and_redact(test_text)
    
    print("Original Text:")
    print(test_text)
    print("\n" + "="*80)
    print("Redacted Text:")
    print(redacted)
    print("\n" + "="*80)
    print("PII Found:")
    for pii_type, items in pii_found.items():
        if items:
            print(f"  {pii_type}: {items}")
    print("\n" + "="*80)
    print("Summary:")
    print(redactor.get_redaction_summary())


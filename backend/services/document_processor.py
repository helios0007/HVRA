import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from PyPDF2 import PdfReader
import hashlib

class DocumentProcessor:
    """
    Process research papers and documents to extract text,
    metadata, and create searchable index entries for RAG.
    """

    def __init__(self, documents_dir: str = None):
        """
        Initialize document processor.

        Args:
            documents_dir: Path to documents folder
        """
        if documents_dir is None:
            documents_dir = os.path.join(
                os.path.dirname(__file__),
                '..',
                'data',
                'documents'
            )

        self.documents_dir = documents_dir
        self.documents = []
        self.document_index = {}

    def process_all_documents(self) -> List[Dict]:
        """
        Process all PDFs in documents folder.

        Returns:
            List of processed document metadata with extracted text
        """
        if not os.path.exists(self.documents_dir):
            print(f"Warning: Documents directory not found at {self.documents_dir}")
            return []

        documents = []
        pdf_files = list(Path(self.documents_dir).glob('*.pdf'))

        print(f"Found {len(pdf_files)} PDF files to process")

        for i, pdf_path in enumerate(pdf_files, 1):
            try:
                doc = self.process_pdf(pdf_path)
                if doc:
                    documents.append(doc)
                    print(f"✓ Processed [{i}/{len(pdf_files)}] {pdf_path.name}")
            except Exception as e:
                print(f"✗ Error processing {pdf_path.name}: {str(e)}")

        self.documents = documents
        self._create_index()

        print(f"Successfully processed {len(documents)} documents")
        return documents

    def process_pdf(self, pdf_path: Path) -> Optional[Dict]:
        """
        Extract text and metadata from a single PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dict with document metadata and extracted text
        """
        try:
            reader = PdfReader(str(pdf_path))

            # Extract text from all pages
            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() + "\n"

            if not full_text.strip():
                return None

            # Extract metadata from PDF
            metadata = reader.metadata or {}

            # Create document entry
            doc = {
                'document_id': self._generate_doc_id(pdf_path),
                'filename': pdf_path.name,
                'full_path': str(pdf_path),
                'extracted_text': full_text[:10000],  # Store first 10k chars
                'full_text_length': len(full_text),
                'page_count': len(reader.pages),
                'title': metadata.get('/Title', pdf_path.stem),
                'author': metadata.get('/Author', 'Unknown'),
                'subject': metadata.get('/Subject', ''),
                'keywords': self._extract_keywords(full_text),
                'concepts': self._extract_concepts(full_text),
                'intervention_types': self._extract_intervention_types(full_text),
                'climate_types': self._extract_climate_types(full_text),
                'thermal_impacts': self._extract_thermal_impacts(full_text)
            }

            return doc

        except Exception as e:
            print(f"Error processing PDF {pdf_path}: {str(e)}")
            return None

    def _generate_doc_id(self, pdf_path: Path) -> str:
        """Generate unique document ID from filename hash."""
        hash_object = hashlib.md5(str(pdf_path).encode())
        return f"doc_{hash_object.hexdigest()[:12]}"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract potential keywords from document."""
        keywords = []

        # Common urban intervention keywords
        key_terms = [
            'urban forest', 'tree canopy', 'green roof', 'cool roof', 'cool pavement',
            'water feature', 'green wall', 'ventilation', 'urban heat', 'thermal',
            'shade', 'vegetation', 'albedo', 'retrofit', 'adaptation', 'mitigation',
            'pavements', 'infrastructure', 'microclimate', 'UTCI', 'thermal comfort',
            'heat island', 'cooling', 'climate', 'pedestrian', 'outdoor'
        ]

        text_lower = text.lower()
        for term in key_terms:
            if term in text_lower:
                keywords.append(term)

        return list(set(keywords))  # Remove duplicates

    def _extract_concepts(self, text: str) -> List[str]:
        """Extract technical concepts and topics."""
        concepts = []

        concept_patterns = {
            'thermal_comfort': ['UTCI', 'thermal comfort', 'heat stress', 'physiological'],
            'cooling': ['cooling', 'temperature reduction', 'cool', 'albedo', 'reflectance'],
            'urban_design': ['urban design', 'streetscape', 'public space', 'density'],
            'vegetation': ['vegetation', 'trees', 'canopy', 'green', 'forest', 'foliage'],
            'water': ['water feature', 'fountain', 'pond', 'evaporative', 'aquatic'],
            'building': ['building', 'roof', 'facade', 'thermal mass', 'envelope'],
            'materials': ['pavement', 'concrete', 'asphalt', 'material', 'surface'],
            'climate': ['climate', 'weather', 'summer', 'peak', 'temperature']
        }

        text_lower = text.lower()
        for concept, keywords in concept_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    concepts.append(concept)
                    break

        return list(set(concepts))

    def _extract_intervention_types(self, text: str) -> List[str]:
        """Extract relevant intervention types mentioned."""
        interventions = []

        intervention_map = {
            'urban_forest': ['tree', 'forest', 'canopy', 'vegetation', 'green', 'planting'],
            'cool_roofs': ['cool roof', 'white roof', 'reflective roof', 'albedo roof'],
            'cool_pavements': ['cool pavement', 'permeable', 'light colored', 'reflective surface'],
            'green_roofs': ['green roof', 'living roof', 'rooftop garden', 'vegetation roof'],
            'green_walls': ['green wall', 'living wall', 'vertical garden', 'facade vegetation'],
            'water_features': ['water feature', 'fountain', 'pond', 'water body', 'canal'],
            'shade_structures': ['shade', 'pergola', 'awning', 'shelter', 'screen'],
            'ventilation': ['ventilation', 'airflow', 'corridor', 'wind', 'circulation']
        }

        text_lower = text.lower()
        for intervention_type, keywords in intervention_map.items():
            for keyword in keywords:
                if keyword in text_lower:
                    interventions.append(intervention_type)
                    break

        return list(set(interventions))

    def _extract_climate_types(self, text: str) -> List[str]:
        """Extract climate types mentioned."""
        climates = []

        climate_keywords = {
            'mediterranean': ['mediterranean', 'dry summer'],
            'subtropical': ['subtropical', 'humid subtropical'],
            'temperate': ['temperate', 'moderate'],
            'tropical': ['tropical', 'equatorial', 'humid tropical'],
            'desert': ['desert', 'arid', 'dry'],
            'alpine': ['alpine', 'mountain', 'high altitude'],
            'continental': ['continental', 'extreme seasonal'],
            'humid_subtropical': ['humid subtropical', 'humid warm']
        }

        text_lower = text.lower()
        for climate, keywords in climate_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    climates.append(climate)
                    break

        return list(set(climates))

    def _extract_thermal_impacts(self, text: str) -> Dict[str, Any]:
        """Extract thermal impact data if mentioned."""
        impacts = {
            'temperature_reductions': [],
            'utci_reductions': [],
            'other_metrics': []
        }

        # Look for temperature reduction patterns
        temp_patterns = [
            r'(\d+\.?\d*)\s*°C\s*reduction',
            r'reduce[ds]?\s*(?:temperature\s+)?(?:by\s+)?(\d+\.?\d*)\s*°C',
            r'(\d+\.?\d*)\s*(?:degree[s]?|°C)\s*(?:cooler|reduction|lower)'
        ]

        for pattern in temp_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            impacts['temperature_reductions'].extend([float(m) for m in matches])

        # Look for UTCI reduction patterns
        utci_patterns = [
            r'UTCI.*?(\d+\.?\d*)\s*°C',
            r'(\d+\.?\d*)\s*°C.*?UTCI'
        ]

        for pattern in utci_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            impacts['utci_reductions'].extend([float(m) for m in matches])

        return impacts

    def _create_index(self):
        """Create searchable index from documents."""
        self.document_index = {
            'total_documents': len(self.documents),
            'by_intervention': {},
            'by_climate': {},
            'by_concept': {}
        }

        # Index by intervention type
        for doc in self.documents:
            for intervention in doc['intervention_types']:
                if intervention not in self.document_index['by_intervention']:
                    self.document_index['by_intervention'][intervention] = []
                self.document_index['by_intervention'][intervention].append(doc['document_id'])

            # Index by climate
            for climate in doc['climate_types']:
                if climate not in self.document_index['by_climate']:
                    self.document_index['by_climate'][climate] = []
                self.document_index['by_climate'][climate].append(doc['document_id'])

            # Index by concept
            for concept in doc['concepts']:
                if concept not in self.document_index['by_concept']:
                    self.document_index['by_concept'][concept] = []
                self.document_index['by_concept'][concept].append(doc['document_id'])

    def save_document_index(self, output_path: str = None) -> str:
        """
        Save processed documents to JSON for use by RAG system.

        Args:
            output_path: Path to save documents index

        Returns:
            Path to saved file
        """
        if output_path is None:
            output_path = os.path.join(
                os.path.dirname(self.documents_dir),
                'documents_index.json'
            )

        output = {
            'documents': self.documents,
            'index': self.document_index,
            'total_processed': len(self.documents)
        }

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"Saved document index to {output_path}")
        return output_path

    def find_documents_by_intervention(self, intervention_type: str) -> List[Dict]:
        """Find documents mentioning specific intervention type."""
        doc_ids = self.document_index['by_intervention'].get(intervention_type, [])
        return [d for d in self.documents if d['document_id'] in doc_ids]

    def find_documents_by_climate(self, climate_type: str) -> List[Dict]:
        """Find documents relevant to specific climate."""
        doc_ids = self.document_index['by_climate'].get(climate_type, [])
        return [d for d in self.documents if d['document_id'] in doc_ids]

    def find_documents_by_concept(self, concept: str) -> List[Dict]:
        """Find documents discussing specific concept."""
        doc_ids = self.document_index['by_concept'].get(concept, [])
        return [d for d in self.documents if d['document_id'] in doc_ids]

    def get_document_summary(self, doc_id: str) -> Optional[Dict]:
        """Get summary information for a specific document."""
        for doc in self.documents:
            if doc['document_id'] == doc_id:
                return {
                    'document_id': doc['document_id'],
                    'filename': doc['filename'],
                    'title': doc['title'],
                    'author': doc['author'],
                    'page_count': doc['page_count'],
                    'keywords': doc['keywords'][:10],  # Top 10 keywords
                    'concepts': doc['concepts'],
                    'intervention_types': doc['intervention_types'],
                    'climate_types': doc['climate_types'],
                    'thermal_impacts': doc['thermal_impacts']
                }
        return None

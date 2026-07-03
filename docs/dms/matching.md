# Document Matching in Hospital AI DMS

This project uses two different matching flows:

1. Patient matching: decide which patient the uploaded document belongs to.
2. Similar case matching: compare the newly uploaded document with old documents from other patients.

## 1. Patient Matching

When a staff member uploads a document, the backend first saves the file privately and extracts text from it.

The system then uses Gemini and local text extraction to read patient details such as:

- Patient name
- UHID / MRN / patient code
- Mobile number
- Age
- Gender
- Document type
- Diagnosis, symptoms, medicines, lab findings, and summary

After extraction, the backend tries to match the document with an existing patient.

The patient matching logic checks extracted patient details against existing patient records. If the match confidence is high enough, the document is automatically linked to that patient.

If no existing patient is confidently matched, but the patient name is found in the document, the system can create a new patient and save the document under that patient.

If the patient name is not found, the document goes to manual review.

## 2. Similar Case Matching

After the uploaded document is processed and linked to a patient, the system performs similar case matching.

This matching is only for the current newly uploaded document.

It does not show old recommendations from previous uploads.

The backend calls:

```python
similar_cases = await process_for_document(current_uploaded_document_id)
```

The service then:

1. Loads the newly uploaded document.
2. Builds clean clinical text from the new document.
3. Generates and saves an embedding for the new document if available.
4. Uses MongoDB Atlas Vector Search to fetch only the top similar old documents.
5. Skips the same document.
6. Skips same-patient documents when both patient IDs are known and equal.
7. Applies clinical safety checks to the vector-search candidates.
8. Saves and returns only matches with similarity greater than or equal to 75%.

## MongoDB Atlas Vector Search Index

Create this Atlas Vector Search index on the `documents` collection:

```json
{
  "name": "clinical_embedding_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      {
        "type": "vector",
        "path": "clinical_embedding",
        "numDimensions": 768,
        "similarity": "cosine"
      }
    ]
  }
}
```

The backend currently uses Gemini `models/text-embedding-004`, which returns 768-dimensional embeddings. If the embedding model changes, update `numDimensions` to match the new model output.

## Clinical Text Used for Matching

The system builds clinical comparison text from fields such as:

- Diagnosis
- Symptoms
- Medicines
- Lab findings
- Radiology findings
- Procedures
- Clinical summary
- Follow-up advice
- Allergies or risk alerts

It avoids non-clinical fields such as:

- File name
- Upload date
- Billing amount
- Hospital address
- Doctor mobile number
- Header/footer text

## Similarity Score

The matcher uses a final score between `0` and `1`.

Examples:

- `0.75` means 75%
- `0.82` means 82%
- `0.90` means 90%

The system saves and displays the score as a percentage:

```python
similarity_score = round(final_score * 100, 2)
```

## 75% Rule

A similar case is shown only when:

```python
final_score >= 0.75
```

If the score is below 75%, the recommendation is not saved and not shown.

Match strength:

- 75% to 84.99%: possible
- 85% and above: strong

## Avoiding False Matches

The system does not trust embedding similarity alone.

Embeddings can sometimes make unrelated medical documents look similar because they share generic clinical wording.

To reduce false matches, the matcher also checks for real clinical evidence, such as meaningful keyword overlap or disease-specific terms.

Examples of disease-specific keyword groups:

- Diabetes: diabetes, sugar, glucose, HbA1c, metformin, insulin
- Asthma: asthma, wheezing, inhaler, salbutamol, breathing
- Dengue: dengue, NS1, platelet, fever, rash
- Migraine: migraine, headache, photophobia, aura, nausea
- UTI: UTI, urinary, urine, dysuria, burning, nitrite, leukocyte

If there is no real clinical overlap, the system does not show a similar case even if the embedding score is high.

## Upload Response

After upload, the backend returns similar cases only for the current uploaded document.

Example when a match is found:

```json
{
  "message": "Document uploaded successfully",
  "document": {
    "document_id": "DOC012"
  },
  "patient": {
    "patient_id": "P012"
  },
  "similar_cases": [
    {
      "new_document_id": "DOC012",
      "matched_document_id": "DOC011",
      "matched_patient_id": "P011",
      "matched_patient_name": "Amit Bansal",
      "similarity_score": 82.4,
      "match_strength": "possible",
      "matched_reasons": [
        "Similar diagnosis found",
        "Similar symptoms found"
      ],
      "warning": "Doctor verification required. This is not a final diagnosis."
    }
  ]
}
```

Example when no current match is found:

```json
{
  "message": "Document uploaded successfully",
  "document": {
    "document_id": "DOC021"
  },
  "patient": {
    "patient_id": "P021"
  },
  "similar_cases": []
}
```

## Frontend Display Rule

The frontend clears old similar cases before each upload:

```ts
setSimilarCases([]);
setUploadResult(null);
```

After upload succeeds, it uses only the current upload response:

```ts
setSimilarCases(response?.similar_cases || []);
```

The similar case card is shown only when the current upload has matches:

```tsx
{similarCases.length > 0 && (
  <SimilarCasesCard similarCases={similarCases} />
)}
```

If `similar_cases` is empty, no similar case section is shown.

## What Happens When a New Document Is Uploaded

When a new document is uploaded, the UI follows this flow:

1. The upload page sends the file to `POST /documents/upload`.
2. The backend saves and processes only this new document.
3. The backend compares this new document with old documents.
4. The backend returns `similar_cases` only for the current uploaded document.
5. The frontend saves those current matches in state.
6. The frontend shows the match card below the uploaded document result only if matches exist.

Example:

File A is uploaded and becomes:

```text
new_document_id = DOC012
```

The backend compares `DOC012` with old documents, such as:

```text
DOC001
DOC002
DOC003
```

If `DOC012` matches `DOC001` by 82%, the upload response contains:

```json
{
  "document": {
    "document_id": "DOC012"
  },
  "similar_cases": [
    {
      "new_document_id": "DOC012",
      "matched_document_id": "DOC001",
      "matched_patient_name": "Amit Bansal",
      "similarity_score": 82.4,
      "match_strength": "possible",
      "warning": "Doctor verification required. This is not a final diagnosis."
    }
  ]
}
```

The frontend then shows:

```text
Possible Similar Clinical Case Found
Matched with: DOC001 / Amit Bansal
Similarity: 82%
Warning: Doctor verification required. This is not a final diagnosis.
```

This match appears only below the result for `DOC012`.

If the next upload is File B and it becomes:

```text
new_document_id = DOC013
```

then the frontend first clears the old matches from File A:

```ts
setSimilarCases([]);
setUploadResult(null);
```

Then it uses only File B's response:

```ts
setSimilarCases(response?.similar_cases || []);
```

If File B does not match anything by 75% or more, the backend returns:

```json
{
  "document": {
    "document_id": "DOC013"
  },
  "similar_cases": []
}
```

In that case, the frontend shows no similar case card.

This prevents old matches from File A from appearing after File B is uploaded.

## Safety Rule

The system must never say:

- Same disease confirmed
- Diagnosis confirmed
- Treatment recommendation
- Medicine recommendation

It should only say:

> Possible similar clinical case found. Doctor verification required. This is not a final diagnosis.

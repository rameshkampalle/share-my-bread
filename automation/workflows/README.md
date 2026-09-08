# Importing the n8n workflows

Import the eight JSON workflows in the order listed in `../README.md`.

After each import, open nodes showing a credential warning and select the existing
n8n credential. Secret values and n8n-generated credential IDs are never stored in
this repository.

Do not activate a workflow until it has passed its manual or test-webhook execution.
The product-indexing workflow intentionally clears only the
`share-my-bread-demo` Pinecone namespace before re-indexing; it does not clear the
entire `enterprise-architecture-rag` index.

The JSON files are generated from `../scripts/generate-workflows.mjs`. Regenerate
them after changing shared model, index, namespace, prompt, or contract settings.

import express from 'express';
import cors from 'cors';
import multer from 'multer';
import crypto from 'crypto';
import dotenv from 'dotenv';
import {
  uploadFileToArweave,
  uploadMetadataToArweave,
} from './arweave-helpers.js';
import { mintEvidenceNft } from './solana-helpers.js';

// Load environment variables
dotenv.config();

const app = express();
const port = process.env.PORT || 3001;

// --- Middleware ---
// Enable Cross-Origin Resource Sharing
app.use(cors());
// Parse JSON bodies
app.use(express.json());
// Configure Multer for file uploads in memory
const storage = multer.memoryStorage();
const upload = multer({ storage: storage });

// --- API Endpoints ---

/**
 * Health check endpoint.
 */
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', timestamp: new Date().toISOString() });
});

/**
 * POST /upload-evidence
 * The main endpoint for uploading tenant evidence.
 *
 * Expects 'multipart/form-data' with:
 * - 'evidenceFile' (the file: PDF, JPG, etc.)
 * - 'tenantWallet' (the tenant's public key string)
 * - 'caseId' (a unique ID for the case)
 * - 'originalFilename' (the original name of the file)
 */
app.post('/upload-evidence', upload.single('evidenceFile'), async (req, res) => {
  try {
    // 1. Validate request
    const { tenantWallet, caseId, originalFilename } = req.body;
    const file = req.file;

    if (!file || !tenantWallet || !caseId || !originalFilename) {
      return res.status(400).json({
        success: false,
        message:
          'Missing required fields: evidenceFile, tenantWallet, caseId, and originalFilename.',
      });
    }

    console.log(`Received evidence upload for case: ${caseId}`);

    // 2. Compute SHA-256 Hash
    const fileBuffer = file.buffer;
    const fileHash = crypto
      .createHash('sha256')
      .update(fileBuffer)
      .digest('hex');
    console.log(`Computed file hash: ${fileHash}`);

    // 3. Upload File to Arweave
    const fileUrl = await uploadFileToArweave(
      fileBuffer,
      file.mimetype,
      caseId
    );

    // 4. Create Metaplex Metadata JSON
    const metadata = {
      name: `Clause Evidence: Case #${caseId}`,
      symbol: 'CLAUSE',
      description: `Immutable evidence submission for tenant-landlord case #${caseId}.`,
      image: 'https://placehold.co/600x600/000000/FFFFFF?text=CLAUSE\\nEVIDENCE', // Placeholder image
      attributes: [
        {
          trait_type: 'Case ID',
          value: caseId,
        },
        {
          trait_type: 'SHA-256 Hash',
          value: fileHash,
        },
        {
          trait_type: 'Original Filename',
          value: originalFilename,
        },
        {
          trait_type: 'Timestamp UTC',
          value: new Date().toISOString(),
        },
      ],
      properties: {
        files: [
          {
            uri: fileUrl,
            type: file.mimetype,
          },
        ],
        category: 'json',
      },
    };

    // 5. Upload Metadata JSON to Arweave
    const metadataUri = await uploadMetadataToArweave(metadata);

    // 6. Mint the NFT Certificate to the Tenant's Wallet
    const nftMintAddress = await mintEvidenceNft(
      metadataUri,
      tenantWallet,
      caseId,
      fileHash
    );

    // 7. Send success response
    res.status(201).json({
      success: true,
      message: 'Evidence successfully certified and minted.',
      caseId: caseId,
      fileHash: fileHash,
      fileUrl: fileUrl,
      metadataUrl: metadataUri,
      nftMintAddress: nftMintAddress,
      explorerUrl: `https://explorer.solana.com/address/${nftMintAddress}?cluster=devnet`,
    });
  } catch (error) {
    console.error('Error in /upload-evidence endpoint:', error);
    res.status(500).json({
      success: false,
      message: 'An internal server error occurred.',
      error: error.message,
    });
  }
});

// --- Start Server ---
app.listen(port, () => {
  console.log(`Clause Backend Server running on http://localhost:${port}`);
  console.log('Using Solana RPC:', process.env.SOLANA_RPC_ENDPOINT);
  console.log('Using Bundlr Node:', process.env.BUNDLR_NODE);
});
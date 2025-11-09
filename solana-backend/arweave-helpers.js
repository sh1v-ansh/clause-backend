import Irys from '@irys/sdk';
import fs from 'fs';
import dotenv from 'dotenv';
dotenv.config();

// Load server wallet
const wallet = JSON.parse(fs.readFileSync(process.env.SERVER_WALLET_PATH, 'utf-8'));
const privateKey = new Uint8Array(wallet);

/**
 * Initializes a connection to the Irys network.
 * @returns {Irys} An Irys client instance.
 */
export const getIrys = () => {
  const irys = new Irys({
    url: process.env.IRYS_NODE,
    token: process.env.IRYS_CURRENCY,
    key: privateKey,
    config: {
      providerUrl: process.env.SOLANA_RPC_ENDPOINT,
    },
  });
  return irys;
};

/**
 * Uploads a file buffer to Arweave via Irys.
 * @param {Buffer} fileBuffer - The file buffer to upload.
 * @param {string} contentType - The MIME type of the file (e.g., 'application/pdf').
 * @param {string} caseId - The case ID to tag the upload with.
 * @returns {string} The Arweave transaction ID (which forms the URL).
 */
export const uploadFileToArweave = async (fileBuffer, contentType, caseId) => {
  try {
    const irys = getIrys();
    const tags = [
      { name: 'Content-Type', value: contentType },
      { name: 'App-Name', value: 'Clause' },
      { name: 'Case-ID', value: caseId },
    ];

    const tx = await irys.upload(fileBuffer, { tags });

    console.log(`File uploaded to Arweave: https://arweave.net/${tx.id}`);
    return `https://arweave.net/${tx.id}`;
  } catch (error) {
    console.error('Error uploading file to Arweave:', error);
    throw new Error('Failed to upload file to Arweave.');
  }
};

/**
 * Uploads Metaplex JSON metadata to Arweave via Irys.
 * @param {object} metadata - The JSON metadata object.
 * @returns {string} The Arweave URL for the JSON file.
 */
export const uploadMetadataToArweave = async (metadata) => {
  try {
    const irys = getIrys();
    const metadataString = JSON.stringify(metadata);

    const tags = [
      { name: 'Content-Type', value: 'application/json' },
      { name: 'App-Name', value: 'Clause-Metadata' },
    ];
    
    // For JSON, we use upload() which is simple
    const tx = await irys.upload(metadataString, { tags });

    console.log(`Metadata uploaded to Arweave: https://arweave.net/${tx.id}`);
    return `https://arweave.net/${tx.id}`;
  } catch (error) {
    console.error('Error uploading metadata to Arweave:', error);
    throw new Error('Failed to upload metadata to Arweave.');
  }
};
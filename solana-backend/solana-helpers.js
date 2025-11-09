import { createUmi } from '@metaplex-foundation/umi-bundle-defaults';
import {
  createNft,
  mplTokenMetadata,
} from '@metaplex-foundation/mpl-token-metadata';
import {
  publicKey,
  generateSigner,
  percentAmount,
  keypairIdentity,
} from '@metaplex-foundation/umi';
import { irysUploader } from '@metaplex-foundation/umi-uploader-irys'; // <-- UPDATED
import fs from 'fs';
import dotenv from 'dotenv';
dotenv.config();

// Load server wallet
const wallet = JSON.parse(fs.readFileSync(process.env.SERVER_WALLET_PATH, 'utf-8'));
const serverKeypair = new Uint8Array(wallet);

/**
 * Initializes the UMI interface for Metaplex.
 * UMI is the new, standard way to interact with Metaplex.
 * @returns {Umi} An UMI instance.
 */
const getUmi = () => {
  const umi = createUmi(process.env.SOLANA_RPC_ENDPOINT)
    .use(mplTokenMetadata())
    .use(irysUploader()); // <-- UPDATED (uses Irys)

  // Set our server wallet as the payer and identity
  const serverUmiKeypair = umi.eddsa.createKeypairFromSecretKey(serverKeypair);
  umi.use(keypairIdentity(serverUmiKeypair));

  return umi;
};

/**
 * Mints an "Evidence Certificate" NFT to the tenant's wallet.
 * @param {string} metadataUri - The Arweave URL of the metadata JSON.
 * @param {string} tenantWalletAddress - The tenant's public key address.
 * @param {string} caseId - The case ID.
 * @param {string} fileHash - The SHA-256 hash of the evidence file.
 * @returns {string} The public key of the newly minted NFT.
 */
export const mintEvidenceNft = async (
  metadataUri,
  tenantWalletAddress,
  caseId,
  fileHash
) => {
  try {
    const umi = getUmi();
    const tenantPublicKey = publicKey(tenantWalletAddress);

    // Generate a new keypair for the NFT mint
    const mint = generateSigner(umi);

    console.log(`Minting Evidence NFT for case ${caseId} to ${tenantWalletAddress}...`);
    console.log(`Metadata URI: ${metadataUri}`);

    // Create the NFT
    const tx = await createNft(umi, {
      mint: mint,
      owner: tenantPublicKey, // The tenant owns this NFT
      name: `Clause Evidence: Case #${caseId}`,
      symbol: 'CLAUSE',
      uri: metadataUri,
      sellerFeeBasisPoints: percentAmount(0), // 0% royalties
      isMutable: false, // Make it immutable!
      collection: null, // No collection for this simple example
    }).sendAndConfirm(umi, {
      confirm: { commitment: 'confirmed' }, // Wait for confirmation
    });

    const nftMintAddress = mint.publicKey.toString();
    console.log(`Successfully minted NFT: ${nftMintAddress}`);
    console.log(
      `View on Solana Explorer: https://explorer.solana.com/address/${nftMintAddress}?cluster=devnet`
    );

    return nftMintAddress;
  } catch (error) {
    console.error('Error minting NFT:', error);
    throw new Error('Failed to mint Evidence NFT.');
  }
};
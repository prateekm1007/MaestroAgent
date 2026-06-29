// src/kms.js — Key Management Service integration.
//
// Provides:
//   - AWS KMS integration for master key management (production)
//   - Local key management with file-based keys (development)
//   - Envelope encryption: generate data keys, encrypt with master key
//   - Key rotation: rotate master keys without re-encrypting all data
//   - Key versioning: old keys remain available for decryption
//
// Environment variables:
//   KMS_PROVIDER       — 'aws' (production) or 'local' (development, default)
//   KMS_MASTER_KEY_ID  — AWS KMS key ID (e.g. arn:aws:kms:us-east-1:...)
//   KMS_REGION         — AWS region (default: us-east-1)
//   KMS_LOCAL_KEY_DIR  — Directory for local keys (default: ./keys/)
//
// How envelope encryption works:
//   1. KMS generates a data key (plaintext + encrypted blob)
//   2. Plaintext data key encrypts the actual data (AES-256-GCM)
//   3. Encrypted data key is stored alongside the ciphertext
//   4. To decrypt: KMS decrypts the data key, then data key decrypts data
//   5. Key rotation: new master key → new encrypted data keys, same plaintext data keys

import crypto from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';

const KMS_PROVIDER = process.env.KMS_PROVIDER || 'local';
const KMS_MASTER_KEY_ID = process.env.KMS_MASTER_KEY_ID || '';
const KMS_REGION = process.env.KMS_REGION || 'us-east-1';
const KMS_LOCAL_KEY_DIR = process.env.KMS_LOCAL_KEY_DIR || './keys';

let kmsClient = null;

// ============================================================================
// KMS PROVIDER INITIALIZATION
// ============================================================================

async function getKMSClient() {
  if (kmsClient) return kmsClient;

  if (KMS_PROVIDER === 'aws') {
    // Lazy import AWS SDK
    let AWS;
    try {
      AWS = (await import('@aws-sdk/client-kms')).KMSClient;
    } catch {
      throw new Error('AWS KMS provider selected but @aws-sdk/client-kms not installed. Run: npm install @aws-sdk/client-kms');
    }
    kmsClient = new AWS({ region: KMS_REGION });
    console.log(`[kms] AWS KMS initialized (key: ${KMS_MASTER_KEY_ID}, region: ${KMS_REGION})`);
  } else {
    // Local provider — ensure key directory exists
    await fs.mkdir(KMS_LOCAL_KEY_DIR, { recursive: true });
    await ensureLocalMasterKey();
    console.log(`[kms] Local KMS initialized (key dir: ${KMS_LOCAL_KEY_DIR})`);
  }

  return kmsClient;
}

// ============================================================================
// LOCAL KMS (development)
// ============================================================================

async function ensureLocalMasterKey() {
  const keyPath = path.join(KMS_LOCAL_KEY_DIR, 'master-key.json');
  try {
    await fs.access(keyPath);
  } catch {
    // Generate new master key
    const masterKey = crypto.randomBytes(32).toString('hex');
    const keyData = {
      keyId: 'local-master-key-v1',
      keyMaterial: masterKey,
      createdAt: new Date().toISOString(),
      version: 1,
    };
    await fs.writeFile(keyPath, JSON.stringify(keyData, null, 2), { mode: 0o600 });
    console.log('[kms] Generated new local master key');
  }
}

async function getLocalMasterKey() {
  const keyPath = path.join(KMS_LOCAL_KEY_DIR, 'master-key.json');
  const data = JSON.parse(await fs.readFile(keyPath, 'utf8'));
  return data;
}

async function getLocalMasterKeyHistory() {
  const historyPath = path.join(KMS_LOCAL_KEY_DIR, 'key-history.json');
  try {
    return JSON.parse(await fs.readFile(historyPath, 'utf8'));
  } catch {
    return [];
  }
}

// ============================================================================
// DATA KEY GENERATION (envelope encryption)
// ============================================================================

/**
 * Generate a data encryption key (DEK).
 * Returns both plaintext DEK (for encrypting data) and encrypted DEK (for storage).
 *
 * @returns {Promise<{ plaintextKey: Buffer, encryptedKey: string, keyId: string }>}
 */
export async function generateDataKey() {
  await getKMSClient();

  if (KMS_PROVIDER === 'aws') {
    return generateAWSDataKey();
  } else {
    return generateLocalDataKey();
  }
}

async function generateAWSDataKey() {
  const { GenerateDataKeyCommand } = await import('@aws-sdk/client-kms');
  const command = new GenerateDataKeyCommand({
    KeyId: KMS_MASTER_KEY_ID,
    KeySpec: 'AES_256',
  });
  const response = await kmsClient.send(command);
  return {
    plaintextKey: Buffer.from(response.Plaintext),
    encryptedKey: Buffer.from(response.CiphertextBlob).toString('base64'),
    keyId: response.KeyId,
  };
}

async function generateLocalDataKey() {
  const masterKeyData = await getLocalMasterKey();
  const masterKey = Buffer.from(masterKeyData.keyMaterial, 'hex');
  const plaintextKey = crypto.randomBytes(32);

  // Encrypt the data key with the master key
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-gcm', masterKey, iv);
  const encryptedKeyBytes = Buffer.concat([cipher.update(plaintextKey), cipher.final()]);
  const authTag = cipher.getAuthTag();

  const encryptedKey = JSON.stringify({
    v: 1,
    iv: iv.toString('hex'),
    data: encryptedKeyBytes.toString('hex'),
    tag: authTag.toString('hex'),
    keyId: masterKeyData.keyId,
  });

  return {
    plaintextKey,
    encryptedKey,
    keyId: masterKeyData.keyId,
  };
}

// ============================================================================
// DATA KEY DECRYPTION (envelope encryption)
// ============================================================================

/**
 * Decrypt an encrypted data key.
 *
 * @param {string} encryptedKey - The encrypted data key (base64 for AWS, JSON for local)
 * @returns {Promise<Buffer>} Plaintext data key
 */
export async function decryptDataKey(encryptedKey) {
  await getKMSClient();

  if (KMS_PROVIDER === 'aws') {
    return decryptAWSDataKey(encryptedKey);
  } else {
    return decryptLocalDataKey(encryptedKey);
  }
}

async function decryptAWSDataKey(encryptedKey) {
  const { DecryptCommand } = await import('@aws-sdk/client-kms');
  const command = new DecryptCommand({
    CiphertextBlob: Buffer.from(encryptedKey, 'base64'),
  });
  const response = await kmsClient.send(command);
  return Buffer.from(response.Plaintext);
}

async function decryptLocalDataKey(encryptedKey) {
  const payload = JSON.parse(encryptedKey);
  const masterKeyData = await getLocalMasterKey();
  const masterKey = Buffer.from(masterKeyData.keyMaterial, 'hex');

  // Try current key first
  try {
    const decipher = crypto.createDecipheriv(
      'aes-256-gcm',
      masterKey,
      Buffer.from(payload.iv, 'hex')
    );
    decipher.setAuthTag(Buffer.from(payload.tag, 'hex'));
    return Buffer.concat([
      decipher.update(Buffer.from(payload.data, 'hex')),
      decipher.final(),
    ]);
  } catch {
    // Try historical keys (for key rotation)
    const history = await getLocalMasterKeyHistory();
    for (const oldKeyData of history) {
      try {
        const oldKey = Buffer.from(oldKeyData.keyMaterial, 'hex');
        const decipher = crypto.createDecipheriv(
          'aes-256-gcm',
          oldKey,
          Buffer.from(payload.iv, 'hex')
        );
        decipher.setAuthTag(Buffer.from(payload.tag, 'hex'));
        return Buffer.concat([
          decipher.update(Buffer.from(payload.data, 'hex')),
          decipher.final(),
        ]);
      } catch {
        continue;
      }
    }
    throw new Error('Failed to decrypt data key with any known master key');
  }
}

// ============================================================================
// ENVELOPE ENCRYPTION (high-level API)
// ============================================================================

/**
 * Encrypt data using envelope encryption.
 * Generates a data key, encrypts the data, returns ciphertext + encrypted key.
 *
 * @param {string} plaintext - Data to encrypt
 * @returns {Promise<string>} JSON-encoded envelope { v, iv, data, tag, encryptedKey, keyId }
 */
export async function envelopeEncrypt(plaintext) {
  if (!plaintext) return null;

  const { plaintextKey, encryptedKey, keyId } = await generateDataKey();

  // Encrypt the data with the data key
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-gcm', plaintextKey, iv);
  const encrypted = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const authTag = cipher.getAuthTag();

  // Zero out the plaintext key from memory
  plaintextKey.fill(0);

  return JSON.stringify({
    v: 2, // envelope encryption version
    iv: iv.toString('hex'),
    data: encrypted.toString('hex'),
    tag: authTag.toString('hex'),
    encryptedKey,
    keyId,
    algorithm: 'aes-256-gcm',
    kmsProvider: KMS_PROVIDER,
  });
}

/**
 * Decrypt data that was encrypted with envelope encryption.
 *
 * @param {string} envelopeJson - JSON-encoded envelope
 * @returns {Promise<string>} Plaintext data
 */
export async function envelopeDecrypt(envelopeJson) {
  if (!envelopeJson) return null;

  const envelope = JSON.parse(envelopeJson);

  // Version 1 = direct encryption (legacy, from src/crypto.js)
  if (envelope.v === 1) {
    return legacyDecrypt(envelope);
  }

  // Version 2 = envelope encryption
  if (envelope.v === 2) {
    const dataKey = await decryptDataKey(envelope.encryptedKey);

    const decipher = crypto.createDecipheriv(
      'aes-256-gcm',
      dataKey,
      Buffer.from(envelope.iv, 'hex')
    );
    decipher.setAuthTag(Buffer.from(envelope.tag, 'hex'));

    const decrypted = Buffer.concat([
      decipher.update(Buffer.from(envelope.data, 'hex')),
      decipher.final(),
    ]);

    // Zero out the data key from memory
    dataKey.fill(0);

    return decrypted.toString('utf8');
  }

  throw new Error(`Unsupported encryption version: ${envelope.v}`);
}

// Legacy decryption for v1 data (from original src/crypto.js)
function legacyDecrypt(envelope) {
  const key = getLegacyEncryptionKey();
  const decipher = crypto.createDecipheriv(
    'aes-256-gcm',
    key,
    Buffer.from(envelope.iv, 'hex')
  );
  decipher.setAuthTag(Buffer.from(envelope.tag, 'hex'));
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(envelope.data, 'hex')),
    decipher.final(),
  ]);
  return decrypted.toString('utf8');
}

function getLegacyEncryptionKey() {
  const key = process.env.ENCRYPTION_KEY;
  if (!key) {
    if (process.env.NODE_ENV === 'production') {
      throw new Error('ENCRYPTION_KEY must be set for legacy decryption');
    }
    return crypto.scryptSync('maestro-dev-key', 'maestro-salt', 32);
  }
  return Buffer.from(key, 'hex');
}

// ============================================================================
// KEY ROTATION
// ============================================================================

/**
 * Rotate the master key.
 * - AWS: creates a new KMS key, updates key ID. Old key remains for decryption.
 * - Local: archives old key, generates new one. Old key available in history.
 *
 * After rotation, new encryptions use the new key.
 * Old data can still be decrypted (old encrypted data keys are decrypted by old key).
 * To re-encrypt old data, use reencryptField().
 *
 * @returns {Promise<{ newKeyId: string, oldKeyId: string }>}
 */
export async function rotateMasterKey() {
  await getKMSClient();

  if (KMS_PROVIDER === 'aws') {
    // AWS: create new key, update env
    const { CreateKeyCommand } = await import('@aws-sdk/client-kms');
    const command = new CreateKeyCommand({
      Description: `Maestro master key — rotated ${new Date().toISOString()}`,
      KeyUsage: 'ENCRYPT_DECRYPT',
      KeySpec: 'SYMMETRIC_DEFAULT',
    });
    const response = await kmsClient.send(command);
    const newKeyId = response.KeyMetadata.KeyId;
    const oldKeyId = KMS_MASTER_KEY_ID;

    console.log(`[kms] AWS KMS key rotated: ${oldKeyId} -> ${newKeyId}`);
    console.log('[kms] Update KMS_MASTER_KEY_ID environment variable to use new key for new encryptions.');
    console.log('[kms] Old key remains available for decryption.');

    return { newKeyId, oldKeyId };
  } else {
    // Local: archive old key, generate new one
    const oldKeyData = await getLocalMasterKey();
    const history = await getLocalMasterKeyHistory();
    history.push(oldKeyData);

    const historyPath = path.join(KMS_LOCAL_KEY_DIR, 'key-history.json');
    await fs.writeFile(historyPath, JSON.stringify(history, null, 2), { mode: 0o600 });

    const newKeyData = {
      keyId: `local-master-key-v${oldKeyData.version + 1}`,
      keyMaterial: crypto.randomBytes(32).toString('hex'),
      createdAt: new Date().toISOString(),
      version: oldKeyData.version + 1,
    };

    const keyPath = path.join(KMS_LOCAL_KEY_DIR, 'master-key.json');
    await fs.writeFile(keyPath, JSON.stringify(newKeyData, null, 2), { mode: 0o600 });

    console.log(`[kms] Local master key rotated: ${oldKeyData.keyId} -> ${newKeyData.keyId}`);

    return { newKeyId: newKeyData.keyId, oldKeyId: oldKeyData.keyId };
  }
}

/**
 * Re-encrypt a field with the current master key.
 * Useful after key rotation to migrate old encrypted data.
 *
 * @param {string} encryptedJson - The encrypted field (v1 or v2)
 * @returns {Promise<string>} Re-encrypted with current key
 */
export async function reencryptField(encryptedJson) {
  if (!encryptedJson) return null;
  const plaintext = await envelopeDecrypt(encryptedJson);
  return await envelopeEncrypt(plaintext);
}

/**
 * Batch re-encrypt multiple fields in a record.
 * Useful for migrating a table after key rotation.
 *
 * @param {object} record - The record with encrypted fields
 * @param {string[]} fieldNames - Names of fields to re-encrypt
 * @returns {Promise<object>} Record with re-encrypted fields
 */
export async function reencryptFields(record, fieldNames) {
  const result = { ...record };
  for (const field of fieldNames) {
    if (result[field]) {
      try {
        result[field] = await reencryptField(result[field]);
      } catch (err) {
        console.warn(`[kms] Failed to re-encrypt field ${field}:`, err.message);
      }
    }
  }
  return result;
}

// ============================================================================
// KMS STATUS
// ============================================================================

export function getKMSStatus() {
  return {
    provider: KMS_PROVIDER,
    keyId: KMS_PROVIDER === 'aws' ? KMS_MASTER_KEY_ID : 'local-master-key',
    region: KMS_PROVIDER === 'aws' ? KMS_REGION : null,
    envelopeEncryption: true,
    keyRotationEnabled: true,
  };
}

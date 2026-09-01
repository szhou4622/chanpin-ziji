import { describe, expect, it } from 'vitest'
import { sha256ArrayBuffer } from './contentHash'

describe('uploaded source content hash', () => {
  it('computes the standard SHA-256 digest from the exact uploaded bytes', async () => {
    const bytes = new TextEncoder().encode('abc')
    await expect(sha256ArrayBuffer(bytes.buffer)).resolves.toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    )
  })
})

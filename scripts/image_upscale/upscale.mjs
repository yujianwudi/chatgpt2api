import sharp from 'sharp'

const width = Number(process.argv[2])
const height = Number(process.argv[3])
const fit = process.argv[4]
const maxPixels = 32 * 1024 * 1024
const maxBytes = 32 * 1024 * 1024

try {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0 || width > 8192 || height > 8192 || width * height > maxPixels || !['contain', 'cover'].includes(fit)) {
    throw new Error('Invalid target')
  }
  const chunks = []
  let bytes = 0
  for await (const chunk of process.stdin) {
    bytes += chunk.length
    if (bytes > maxBytes) throw new Error('Input limit')
    chunks.push(chunk)
  }
  sharp.cache(false)
  sharp.concurrency(1)
  const pipeline = sharp(Buffer.concat(chunks), { limitInputPixels: maxPixels })
  const metadata = await pipeline.metadata()
  if ((metadata.pages || 1) > 1) throw new Error('Animated source')
  pipeline.rotate().resize(width, height, {
    fit,
    position: 'centre',
    background: metadata.hasAlpha ? { r: 0, g: 0, b: 0, alpha: 0 } : '#ffffff',
    kernel: sharp.kernel.lanczos3,
  })
  if (metadata.format === 'jpeg') pipeline.jpeg({ quality: 95, chromaSubsampling: '4:4:4' })
  else if (metadata.format === 'webp') pipeline.webp({ quality: 95, effort: 3 })
  else pipeline.png({ compressionLevel: 3 })
  process.stdout.write(await pipeline.toBuffer())
} catch {
  process.stderr.write('Sharp enlargement failed')
  process.exitCode = 1
}

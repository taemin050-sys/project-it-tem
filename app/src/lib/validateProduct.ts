import type { ProductForm } from '../store/projectStore'
import { validateImages, type Limits } from './validateImages.ts'

export type ProductErrors = Partial<Record<'images' | 'references' | 'product_name' | 'features' | 'photo_verified', string>>

export function validateProduct(
  images: File[],
  references: File[],
  product: ProductForm,
  limits: { product: Limits; reference: Limits },
): ProductErrors {
  const errors: ProductErrors = {}
  const imageErrors = validateImages(images, limits.product, '제품 사진')
  if (imageErrors.length > 0) errors.images = imageErrors.join(' ')
  const refErrors = validateImages(references, limits.reference, '배경 참고 사진')
  if (refErrors.length > 0) errors.references = refErrors.join(' ')
  if (!product.product_name.trim()) errors.product_name = '제품명을 입력해 주세요.'
  if (!product.features.trim()) errors.features = '제품 특징을 입력해 주세요.'
  if (!product.photo_verified) errors.photo_verified = '사진 사용 권한을 확인해 주세요.'
  return errors
}

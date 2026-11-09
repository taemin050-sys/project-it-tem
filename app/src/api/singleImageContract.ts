/** PM Track A: FE #26 selects one mode and one ratio per immutable Live Job.
 * The Image Owner multi-candidate examples are not accepted REST contracts.
 * No candidate count, mix array, or batch flags may be serialized here.
 */
import type {Ratio} from '../config'
import type {GenerationMode} from '../store/projectStore'
import type {ProductInput} from '../types/textSchema'

export const SINGLE_IMAGE_MODES=['composed','freeform'] as const
export const SINGLE_IMAGE_RATIOS=['3:4','4:5','9:16'] as const

export function frozenSingleImageInput(jobId:string,product:ProductInput,
                                       ratio:Ratio,mode:GenerationMode) {
  if(!/^[0-9a-f]{32}$/.test(jobId) ||
      !SINGLE_IMAGE_RATIOS.includes(ratio) ||
      !SINGLE_IMAGE_MODES.includes(mode))
    throw Error('PM_IMAGE_SINGLE_MODE_RATIO_INVALID')
  return {customer_request_id:'product-live-'+jobId,product,
    image_size:ratio,generation_mode:mode}
}

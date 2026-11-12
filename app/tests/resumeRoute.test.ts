import test from 'node:test'
import assert from 'node:assert/strict'
import {resumePath,resumeLabel} from '../src/lib/resumeRoute.ts'
import type {LiveState} from '../src/api/liveMapping.ts'

test('all live states map to review or export without mutation',()=>{
  const states:Record<LiveState,string>={
    INPUT_STORED:'/create/copy',
    COPY_REVIEW_REQUIRED:'/create/copy',
    COPY_REJECTED:'/create/copy',
    COPY_APPROVED:'/create/draft',
    PROMPT_READY:'/create/draft',
    IMAGE_REVIEW_REQUIRED:'/create/draft',
    IMAGE_APPROVED:'/create/draft',
    IMAGE_REJECTED:'/create/draft',
    COMPLETED:'/create/export',
  }
  for(const [state,path] of Object.entries(states) as [LiveState,string][]){
    assert.equal(resumePath(state),path)
    assert.ok(resumeLabel(state).length>0)
  }
})

import fs from 'node:fs/promises';
import path from 'node:path';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import {finalizePresentation,applyPresentationChartFont} from '/home/nurzhan/.codex/plugins/cache/openai-primary-runtime/presentations/26.1104.22356/skills/presentations/container_tools/artifact_tool_utils.mjs';

const workspaceDir=process.cwd();
const build=path.join(workspaceDir,'artifacts/pitch/.build');
const out=path.join(workspaceDir,'artifacts/pitch/output');
const SKILL='/home/nurzhan/.codex/plugins/cache/openai-primary-runtime/presentations/26.1104.22356/skills/presentations';
const PY='/home/nurzhan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const candidatePath=path.join(build,'candidate.pptx');
const result=await finalizePresentation({workspaceDir,candidatePath,finalPath:path.join(out,'Modus-Feedback-Pitch.pptx'),pythonExecutable:PY,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],requiredNativeChartOwnerSlides:[3,10],requiredNativeTableOwnerSlides:[],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
console.log(JSON.stringify(result));

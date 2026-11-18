import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const workspaceDir = path.resolve("../..");
const buildDir = path.resolve(".");
const skillDir =
  "/Users/zhengrui/.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11217/skills/presentations";
const pythonExecutable =
  "/Users/zhengrui/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const draftPath = path.join(buildDir, "ttc-enterprise-draft.pptx");
const stagingDir = path.join(workspaceDir, ".codex-finalizer");
const candidatePath = path.join(stagingDir, "ttc-enterprise-candidate.pptx");
const finalPath = path.join(workspaceDir, "output", "TTC-企业级AI招聘操作系统.pptx");
const receiptPath = path.join(stagingDir, "ttc-enterprise-final.validation.json");

await fs.mkdir(stagingDir, { recursive: true });
await fs.mkdir(path.dirname(finalPath), { recursive: true });
await fs.copyFile(draftPath, candidatePath);

const { finalizePresentation } = await import(
  pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href
);

const result = await finalizePresentation({
  explicitTotalSlideCount: 12,
  requiredNativeTableOwnerSlides: [8],
  requiredNativeChartOwnerSlides: [],
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable,
  integrityValidatorPath: path.join(
    skillDir,
    "container_tools/inspect_presentation_package_integrity.py",
  ),
  layoutValidatorPath: path.join(
    skillDir,
    "container_tools/inspect_presentation_layout_geometry.py",
  ),
  layoutArgs: [
    "--expected-slide-size-emu",
    "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
    "--require-native-table-slide",
    "8",
  ],
  fontPolicy: {
    basis: "design",
    families: ["Hiragino Sans GB", "Menlo"],
  },
  verifyArtifactToolImport: true,
  receiptPath,
});

console.log(JSON.stringify({ result, finalPath, receiptPath }));

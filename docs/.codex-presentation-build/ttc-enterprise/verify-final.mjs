import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const finalPath = path.resolve(
  "../../output/TTC-企业级AI招聘操作系统.pptx",
);
const outDir = path.resolve("final-preview");
await fs.mkdir(outDir, { recursive: true });

const presentation = await PresentationFile.importPptx(
  await FileBlob.load(finalPath),
);
const snapshot = await presentation.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes",
  maxChars: 20000,
});
await fs.writeFile(
  path.join(outDir, "final-inspect.ndjson"),
  snapshot.ndjson,
  "utf8",
);

for (const [index, slide] of presentation.slides.items.entries()) {
  const preview = await presentation.export({
    slide,
    format: "png",
    scale: 1.25,
  });
  await fs.writeFile(
    path.join(outDir, `final-${String(index + 1).padStart(2, "0")}.png`),
    Buffer.from(await preview.arrayBuffer()),
  );
}
console.log(
  JSON.stringify({
    finalPath,
    slides: presentation.slides.items.length,
    previewDir: outDir,
  }),
);

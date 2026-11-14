# 简历数据资产

仓库外的归档包含导出的简历 HTML 样本、提取报告、结构分组报告，以及与 `resume_html/resume0.html` 内容相同的 `test.html`。这些文件用于回看分析结果和原始样本。线上匹配读取已解析的简历文本、岗位描述和模型文件。

## 模型读取的数据

- `resume-match` 的分类训练默认读取 `resume-match/data/archive/archive/Resume/Resume.csv` 的简历文本和类别，以及 `resume-match/splits/split.csv` 的固定划分。
- `resume-match` 的简历与岗位配对训练还读取 `jd/jobs_24.yaml` 和中文样本 `data/resume_zh.jsonl`，可用 `--no-zh` 跳过中文样本。GBDT 训练从 `data/` 或 `synth/` 读取简历和划分 CSV，并读取 `jd/jobs_24.yaml`。这些路径相对于 `resume-match/`。
- `resume_html/jobfit_project` 训练从 `--data-dir` 指定的目录读取 `resumes.csv` 和 `tag.csv`，并在文件存在时读取 `resume_experiences.csv`、`structure_groups.csv` 和 `jobs.csv`。CSV 中的 HTML 文件名用于标记来源和提取样本编号。

## 恢复归档

1. 在 ZIP 所在目录运行 `shasum -a 256 -c <归档名>.zip.sha256`，然后解包到单独目录。
2. 在解包目录运行 `shasum -a 256 -c --quiet SHA256SUMS`。`MANIFEST.tsv` 记录每个文件的原始相对路径、字节数和 SHA-256。
3. 在解包目录打开 `resume_html/structure_report.html`，可沿相对链接回看样本。如需在仓库内恢复，把解包的 `resume_html/` 内容放回仓库的同名目录，把 `test.html` 放回仓库根目录。

`dataprocess.py` 的 HTML 导出代码目前处于注释状态。恢复原始 HTML 请使用归档。

项目展示页现位于 [`docs/demo/project-showcase.html`](demo/project-showcase.html)，可在浏览器中直接打开。

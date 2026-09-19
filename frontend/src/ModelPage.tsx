import { useCallback, useEffect, useRef, useState } from "react";

type Target = "item" | "user";
type Kind = "lr" | "fm" | "lightgbm";
type Selection = { user: string[]; candidate: string[] };
type Feature = { id: string; name: string; entity: string; family: string; group: string; description: string; value_type: string; definition_version: number; status: string; scenes?: string[]; materialization: { online: boolean; offline: boolean } };
type Taxon = { id: string; label: string; description?: string };
type Catalog = { catalog_version: number; features: Feature[]; taxonomy: { families: Taxon[]; scenes: Taxon[] }; models: Record<Kind, Record<Target, Selection>> };
type Release = { version: string; scene: string; model_type: Kind; target_type: Target; feature_selection?: Selection; feature_set?: string; input_dim?: number; training_config?: Record<string, unknown>; metrics?: { auc?: number; samples?: number }; gate?: { passed: boolean } };
type Releases = { active_version: string | null; active: Release | null; releases: Release[] };
type Runtime = { ready: boolean; model_loaded: boolean; user_model_loaded: boolean; model?: {path: string}; user_model?: {path: string} };
type Run = { dag_run_id: string; state: string; start_date?: string; conf?: { model_type?: Kind; target_type?: Target; revision?: string } };

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
  return data;
}

export default function ModelPage() {
  const [tab, setTab] = useState<"features" | "training" | "deployment">("training");
  const [target, setTarget] = useState<Target>("item");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [releases, setReleases] = useState<Releases | null>(null);
  const [runtime, setRuntime] = useState<Runtime | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [selections, setSelections] = useState<Record<string, Selection>>({});
  const [training, setTraining] = useState({ model_type: "lr" as Kind, business_date: new Date().toISOString().slice(0, 10), revision: `r${Date.now()}`, scene: "global", epochs: 5, batch_size: 256, validation_ratio: .2, min_auc: 0, factor_dim: 8 });
  const key = `${training.model_type}:${target}`;
  const supported = catalog?.models[training.model_type][target];
  const selected = selections[key] || supported || { user: [], candidate: [] };
  const featureById = new Map(catalog?.features.map((feature) => [feature.id, feature]) || []);
  const families = catalog?.taxonomy.families || [];
  const report = (reason: unknown) => setError(reason instanceof Error ? reason.message : "操作失败");
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    const results = await Promise.allSettled([
      request<Catalog>("/api/models/features"),
      request<Releases>(`/api/models/releases/global?target_type=${target}`),
      request<{ dag_runs?: Run[] }>("/api/models/training"),
      request<Runtime>("/api/models/runtime"),
    ]);
    if (current !== generation.current) return;
    if (results[3].status === "fulfilled") setRuntime(results[3].value); else setRuntime(null);
    if (results[0].status === "fulfilled") setCatalog(results[0].value); else report(results[0].reason);
    if (results[1].status === "fulfilled") setReleases(results[1].value); else report(results[1].reason);
    if (results[2].status === "fulfilled") setRuns(results[2].value.dag_runs || []); else report(results[2].reason);
  }, [target]);
  useEffect(() => { setReleases(null); void load(); return () => { generation.current++; }; }, [load]);
  useEffect(() => { if (tab !== "training") return; const timer = window.setInterval(() => void load(), 10000); return () => window.clearInterval(timer); }, [load, tab]);

  function toggle(role: keyof Selection, id: string, checked: boolean) {
    setSelections({ ...selections, [key]: { ...selected, [role]: checked ? [...selected[role], id] : selected[role].filter((value) => value !== id) } });
  }
  async function train() {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await request<Run>("/api/models/training", { ...training, target_type: target, feature_selection: selected });
      setMessage(`训练已提交：${result.dag_run_id}。完成后请到在线部署选择版本发布。`);
      await load();
    } catch (reason) { report(reason); } finally { setBusy(false); }
  }
  async function deploy(release?: Release) {
    if (!window.confirm(release ? `确认部署 ${release.scene}/${release.version}？` : "确认回滚到另一个保留版本？")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await request<Releases>(`/api/models/releases/${release ? "publish" : "rollback"}`, release ? { scene: release.scene, version: release.version, target_type: target } : { scene: "global", target_type: target });
      setMessage(`部署完成：${result.active_version}`); await load();
    } catch (reason) { report(reason); } finally { setBusy(false); }
  }
  function copy(release: Release) {
    if (!release.feature_selection) return;
    setTraining({ ...training, epochs: Number(release.training_config?.epochs ?? training.epochs), batch_size: Number(release.training_config?.batch_size ?? training.batch_size), validation_ratio: Number(release.training_config?.validation_ratio ?? training.validation_ratio), factor_dim: Number(release.training_config?.factor_dim ?? training.factor_dim), min_auc: Number(release.training_config?.min_auc ?? training.min_auc), model_type: release.model_type, scene: release.training_config?.scene as string || release.scene, revision: `r${Date.now()}` });
    setSelections({ ...selections, [`${release.model_type}:${target}`]: release.feature_selection });
    setTab("training");
  }
  const unsupported = supported && (Object.keys(selected) as (keyof Selection)[]).some((role) => selected[role].some((id) => !supported[role].includes(id)));
  return <main>
    <header><div><p className="eyebrow">MODEL LIFECYCLE</p><h1>Rank Model</h1><p className="subtitle">共享特征 · 离线训练 · 版本化在线部署</p></div>
      <div className="actions"><select aria-label="排序目标" disabled={busy} value={target} onChange={(event) => setTarget(event.target.value as Target)}><option value="item">物品排序</option><option value="user">用户排序</option></select><button onClick={() => { setError(""); void load(); }}>↻ 刷新</button></div></header>
    <div className="model-tabs">{([ ["features", "全局特征中心"], ["training", "离线训练"], ["deployment", "在线部署"] ] as const).map(([value, label]) => <button key={value} className={tab === value ? "selected" : ""} onClick={() => setTab(value)}>{label}</button>)}</div>
    {error && <div role="alert" className="notice error page-notice">{error}</div>}{message && <div role="status" className="notice success page-notice">{message}</div>}
    {tab === "features" && <section className="panel feature-catalog"><div className="panel-title"><span>全局特征目录 · v{catalog?.catalog_version || "—"}</span><input aria-label="搜索特征" placeholder="搜索特征名称" value={query} onChange={(event) => setQuery(event.target.value)}/></div><p>展示已声明的计算与模型支持能力。新增特征需先完成工程实现和验证；数据是否可用会在部署加载时检查。</p>
      <table><thead><tr><th>特征</th><th>实体 / 类别</th><th>定义版本 / 类型</th><th>离线 / 在线实现</th><th>支持模型</th></tr></thead><tbody>{catalog?.features.filter((feature) => feature.id.includes(query) || feature.description.includes(query)).sort((a, b) => `${a.family}:${a.entity}:${a.id}`.localeCompare(`${b.family}:${b.entity}:${b.id}`)).map((feature) => <tr key={feature.id}><td><strong>{feature.id}</strong><small>{feature.description}</small></td><td>{feature.entity} · {families.find((family) => family.id === feature.family)?.label || feature.family}</td><td>v{feature.definition_version} · {feature.value_type}</td><td>{feature.materialization.offline ? "已实现" : "未实现"} / {feature.materialization.online ? "已实现" : "未实现"}</td><td>{(["lr", "fm", "lightgbm"] as Kind[]).filter((model) => Object.values(catalog.models[model]).some((roles) => [...roles.user, ...roles.candidate].includes(feature.id))).map((model) => model.toUpperCase()).join(" / ") || "暂无"}</td></tr>)}</tbody></table>
    </section>}
    {tab === "training" && <>
      <section className="panel config-panel"><div className="panel-title"><span>创建离线训练任务</span><small>生成版本后手动部署</small></div><fieldset disabled={busy} className="model-training-fields"><div className="config-grid">
        <label>模型类型<select value={training.model_type} onChange={(event) => setTraining({ ...training, model_type: event.target.value as Kind })}><option value="lr">LR</option><option value="fm">FM</option><option value="lightgbm">LightGBM</option></select></label>
        <label>业务日期<input type="date" value={training.business_date} onChange={(event) => setTraining({ ...training, business_date: event.target.value })}/></label>
        <label>版本修订号<input value={training.revision} onChange={(event) => setTraining({ ...training, revision: event.target.value })}/></label>
        <label>训练场景范围<input value={training.scene} onChange={(event) => setTraining({ ...training, scene: event.target.value })}/><small>global 使用全部场景；部署对该排序目标全局生效</small></label>
        <label>训练轮数<input type="number" min="1" max="100" value={training.epochs} onChange={(event) => setTraining({ ...training, epochs: Number(event.target.value) })}/></label>
        <label>批量大小<input type="number" min="1" max="65536" value={training.batch_size} onChange={(event) => setTraining({ ...training, batch_size: Number(event.target.value) })}/></label>
        <label>验证集比例<input type="number" min="0.01" max="0.99" step="0.01" value={training.validation_ratio} onChange={(event) => setTraining({ ...training, validation_ratio: Number(event.target.value) })}/></label>
        <label>最低 AUC<input type="number" min="0" max="1" step="0.01" value={training.min_auc} onChange={(event) => setTraining({ ...training, min_auc: Number(event.target.value) })}/></label>
        {training.model_type === "fm" && <label>FM 隐向量维度<input type="number" min="1" max="256" value={training.factor_dim} onChange={(event) => setTraining({ ...training, factor_dim: Number(event.target.value) })}/></label>}
      </div><div className="feature-selection">{(["user", "candidate"] as const).map((role) => <fieldset key={role}><legend>{role === "user" ? "源用户特征" : target === "item" ? "候选物品特征" : "候选用户特征"}（{selected[role].length}）</legend>{families.map((family) => { const ids = supported?.[role].filter((id) => featureById.get(id)?.family === family.id) || []; if (!ids.length) return null; return <details className="feature-family" key={family.id} open={family.id === "attribute" || family.id === "statistical"}><summary>{family.label}<small>{family.description}</small><span>{ids.filter((id) => selected[role].includes(id)).length}/{ids.length}</span></summary>{ids.map((id) => <label key={id} title={featureById.get(id)?.description}><input type="checkbox" checked={selected[role].includes(id)} onChange={(event) => toggle(role, id, event.target.checked)}/><span>{featureById.get(id)?.name || id}<small>{id}</small></span></label>)}</details>; })}</fieldset>)}</div></fieldset>
      {unsupported && <p role="alert">复制的版本包含当前不再支持的特征，请重新选择配置。</p>}
      <div className="config-actions"><span>每侧至少选择一个特征；输入编码在训练时确定并随版本保存。</span><button className="primary" disabled={busy || !catalog || !!unsupported || !selected.user.length || !selected.candidate.length} onClick={() => void train()}>{busy ? "提交中…" : "开始训练"}</button></div></section>
      <section className="panel training-runs"><div className="panel-title"><span>最近训练任务</span><small>每 10 秒刷新</small></div>{runs.filter((run) => (run.conf?.target_type || "item") === target).map((run) => <div key={run.dag_run_id}><code>{run.dag_run_id}</code><span>{run.conf?.model_type?.toUpperCase()} · {run.conf?.revision}</span><strong>{run.state}</strong></div>)}{!runs.length && <p>暂无训练任务</p>}</section>
    </>}
    {tab === "deployment" && <>
      <section className="graph-status"><div><span>发布记录</span><strong>{releases?.active ? `${releases.active.scene}/${releases.active_version}` : "尚无发布记录"}</strong></div><div><span>生效范围</span><strong>全局 {target === "item" ? "物品排序" : "用户排序"}</strong></div><div><span>实际运行状态</span><strong>{runtime ? (target === "item" ? runtime.model_loaded : runtime.user_model_loaded) ? runtime.ready ? "已加载 · 就绪" : "已加载 · 未就绪" : "模型未加载" : "无法获取"}</strong></div></section>
      <section className="panel model-releases"><div className="panel-title"><span>已训练版本</span><button disabled={!releases?.active || busy} onClick={() => void deploy()}>回滚保留版本</button></div>
      <div className="model-version-list">{releases?.releases.map((release) => { const active = (target === "item" ? runtime?.model : runtime?.user_model)?.path.includes(`/${release.scene}/${release.version}/`) || false; return <article key={`${release.scene}/${release.version}`} className={active ? "active" : ""}><div className="model-version-title"><strong>{release.scene}/{release.version}</strong><span>{release.model_type.toUpperCase()} · AUC {release.metrics?.auc?.toFixed(4) ?? "—"} · 样本 {release.metrics?.samples ?? "—"} · 维度 {release.input_dim ?? "—"}</span><button disabled={busy || active || !release.gate?.passed} onClick={() => void deploy(release)}>{active ? "当前部署" : "部署此版本"}</button></div>
      <details><summary>查看固定特征与训练配置</summary>{release.feature_selection ? <>{(["user", "candidate"] as const).map((role) => <p key={role}><b>{role === "user" ? "源用户" : "候选对象"}：</b>{release.feature_selection![role].join("、")}</p>)}<button onClick={() => copy(release)}>复制特征配置并重新训练</button></> : <p>历史版本未记录可复制的特征清单，保留原编码产物。</p>}<pre>{JSON.stringify(release.training_config || {}, null, 2)}</pre></details></article>; })}{releases?.releases.length === 0 && <div className="empty">训练评估通过后，版本将在这里显示。</div>}</div></section>
    </>}
    <footer>OpenRec Console · 特征开发与验证完成后才能进入模型训练和部署</footer>
  </main>;
}

import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Algorithm = "hot" | "new" | "i2i";
type DailyAlgorithm = Algorithm | "embedding";
type Release = { index: string; active: boolean; documents: number };
type ReleaseSet = {
  algorithm: Algorithm;
  active_indexes: string[];
  indexes: string[];
  releases: Release[];
};

const algorithms: Algorithm[] = ["hot", "new", "i2i"];
const dailyAlgorithms: DailyAlgorithm[] = ["hot", "new", "i2i", "embedding"];
const labels: Record<DailyAlgorithm, string> = {
  hot: "热门召回",
  new: "新品召回",
  i2i: "I2I 召回",
  embedding: "Embedding 召回",
};

const modules = [
  ["召回索引", "已启用", "recall"],
  ["实体排查", "已启用", "entities"],
  ["Serving Graph", "已启用", "serving"],
  ["离线任务 DAG", "已启用", "dag"],
  ["监控大盘", "已启用", "monitor"],
  ["Airflow 自动化", "已启用", "airflow"],
  ["Rank Model", "已启用", "model"],
] as const;

type EntityKind = "user" | "item" | "event";
type EventResult = {id?: string; score?: number};
type EntityEventResult = {user_id: string; scene: string; event_type: string; events: EventResult[]};

function EntityQueryPage() {
  const [kind, setKind] = useState<EntityKind>("user");
  const [entityId, setEntityId] = useState("user_0");
  const [scene, setScene] = useState("scene_0");
  const [eventType, setEventType] = useState("click");
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function query() {
    if (!entityId.trim() || (kind === "event" && (!scene.trim() || !eventType.trim()))) {
      setError("请填写完整查询条件"); return;
    }
    setBusy(true); setError(""); setResult(null);
    try {
      const path = kind === "user" ? `/api/entities/users/${encodeURIComponent(entityId.trim())}`
        : kind === "item" ? `/api/entities/items/${encodeURIComponent(entityId.trim())}`
        : `/api/entities/events?${new URLSearchParams({user_id: entityId.trim(), scene: scene.trim(), event_type: eventType.trim()})}`;
      setResult(await api<unknown>(path));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "实体查询失败"); }
    finally { setBusy(false); }
  }

  const eventResult = kind === "event" && result ? result as EntityEventResult : null;
  return <main><header><div><p className="eyebrow">DATA INSPECTOR</p><h1>实体排查</h1>
    <p className="subtitle">按在线服务的真实读取口径查询 User、Item 与 Event</p></div></header>
    <section className="entity-query panel"><div className="entity-tabs">{(["user", "item", "event"] as EntityKind[]).map((item) =>
      <button key={item} className={kind === item ? "active" : ""} onClick={() => { setKind(item); setResult(null); setError(""); }}>{item.toUpperCase()}</button>)}</div>
      <div className="query-form"><label>{kind === "item" ? "Item ID" : "User ID"}<input value={entityId} onChange={(event) => setEntityId(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void query(); }}/></label>
        {kind === "event" && <><label>Scene<input value={scene} onChange={(event) => setScene(event.target.value)}/></label><label>Event Type<select value={eventType} onChange={(event) => setEventType(event.target.value)}><option>click</option><option>expose</option><option>buy</option><option>collect</option><option>stay</option></select></label></>}
        <button className="primary" disabled={busy} onClick={() => void query()}>{busy ? "查询中…" : "查询"}</button></div></section>
    {error && <div className="notice error page-notice entity-notice">{error}</div>}
    <section className="panel entity-result"><div className="panel-title"><span>查询结果</span><small>{result ? "来自 rec-server / Redis" : "等待查询"}</small></div>
      {!result && !error && <div className="empty">输入实体标识开始排查</div>}
      {eventResult && <div className="event-summary"><span>USER <b>{eventResult.user_id}</b></span><span>SCENE <b>{eventResult.scene}</b></span><span>TYPE <b>{eventResult.event_type}</b></span><span>COUNT <b>{eventResult.events?.length || 0}</b></span></div>}
      {eventResult ? <div className="event-table"><div className="event-row head"><span>#</span><span>Item ID</span><span>Event Time</span><span>Readable Time</span></div>
        {(eventResult.events || []).map((event, index) => <div className="event-row" key={`${event.id}-${index}`}><span>{index + 1}</span><code>{event.id || "—"}</code><code>{event.score ?? "—"}</code><span>{event.score ? new Date(event.score * 1000).toLocaleString() : "—"}</span></div>)}
        {eventResult.events?.length === 0 && <div className="empty">该条件下没有事件</div>}</div>
        : result !== null && <pre className="entity-json">{JSON.stringify(result, null, 2)}</pre>}</section>
    <section className="query-help"><article><strong>User</strong><p>当前用户画像、场景及扩展属性。</p></article><article><strong>Item</strong><p>物品状态、类目、时间和扩展属性。</p></article><article><strong>Event</strong><p>Redis 有序集合中的 Item 与事件时间。</p></article></section>
    <footer>OpenRec Console · Read-only diagnostics through rec-server QueryService</footer></main>;
}

type GraphNode = { name: string; clazz: string; configClazz?: string | null; open: boolean; timeout: number; content: unknown };
type GraphEdge = { from: string; to: string };
type ServingGraph = { nodes: GraphNode[]; edges: GraphEdge[] };
type GraphRelease = { version: string; published_at?: string; checksum?: string };

function MonitorPage() {
  const grafanaUrl = "/grafana/d/openrec-rec-server-api/openrec-rec-server-api?orgId=1&kiosk";
  return <main><header><div><p className="eyebrow">OBSERVABILITY</p><h1>监控大盘</h1>
    <p className="subtitle">rec-server 推送与推荐接口的流量、延迟、错误和数据规模</p></div>
    <a className="refresh monitor-link" href={grafanaUrl.replace("&kiosk", "")} target="_blank" rel="noreferrer">在 Grafana 中打开 ↗</a></header>
    <section className="monitor-summary"><article><strong>Push API</strong><span>Item / User / Event QPS、P95 延迟、错误和推送规模</span></article>
      <article><strong>Recommend API</strong><span>QPS、P95 延迟、错误率和推荐结果规模</span></article>
      <article><strong>Data Source</strong><span>Prometheus · 15 秒采集 · Grafana 10 秒刷新</span></article></section>
    <section className="panel monitor-panel"><iframe title="OpenRec rec-server API dashboard" src={grafanaUrl} /></section>
    <footer>OpenRec Console · Grafana dashboard backed by Prometheus metrics</footer></main>;
}

function graphLayout(graph: ServingGraph) {
  const level = new Map(graph.nodes.map((node) => [node.name, 0]));
  const incoming = new Map(graph.nodes.map((node) => [node.name, 0]));
  graph.edges.forEach((edge) => incoming.set(edge.to, (incoming.get(edge.to) || 0) + 1));
  const queue = graph.nodes.filter((node) => incoming.get(node.name) === 0).map((node) => node.name);
  while (queue.length) {
    const name = queue.shift()!;
    graph.edges.filter((edge) => edge.from === name).forEach((edge) => {
      level.set(edge.to, Math.max(level.get(edge.to) || 0, (level.get(name) || 0) + 1));
      incoming.set(edge.to, (incoming.get(edge.to) || 0) - 1);
      if (incoming.get(edge.to) === 0) queue.push(edge.to);
    });
  }
  const trigger = graph.nodes.find((node) => node.name.toLowerCase() === "usertrigger")?.name;
  if (trigger) {
    level.set(trigger, 0);
    graph.nodes.forEach((node) => {
      if (node.name !== trigger && (level.get(node.name) || 0) === 0) level.set(node.name, 1);
    });
  }
  const layers = new Map<number, string[]>();
  graph.nodes.forEach((node) => layers.set(level.get(node.name) || 0, [...(layers.get(level.get(node.name) || 0) || []), node.name]));
  const maxColumns = Math.max(1, ...Array.from(layers.values()).map((items) => items.length));
  const positions = new Map<string, {x: number; y: number}>();
  layers.forEach((items, layer) => items.forEach((name, column) => positions.set(name, {
    x: 32 + column * 178 + (maxColumns - items.length) * 89, y: 34 + layer * 110,
  })));
  return {positions, width: Math.max(760, 70 + maxColumns * 178), height: Math.max(360, 86 + layers.size * 110)};
}

function ServingGraphPage() {
  const [graph, setGraph] = useState<ServingGraph | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [checksum, setChecksum] = useState<string | null>(null);
  const [history, setHistory] = useState<GraphRelease[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("{}");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState(1);
  const graphViewport = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await api<{version: string | null; checksum: string | null; graph: ServingGraph; history: GraphRelease[]}>("/api/serving-graph");
      setGraph(result.graph); setVersion(result.version); setChecksum(result.checksum); setHistory(result.history || []);
      const name = selected || result.graph.nodes[0]?.name || ""; setSelected(name);
      const node = result.graph.nodes.find((item) => item.name === name);
      setContent(JSON.stringify(node?.content ?? {}, null, 2));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法读取在线 Serving Graph"); }
  }, []);
  useEffect(() => { void load(); }, []);

  const node = graph?.nodes.find((item) => item.name === selected);
  const layout = graph ? graphLayout(graph) : null;
  function fitGraph() {
    if (!layout || !graphViewport.current) return;
    const viewport = graphViewport.current;
    setZoom(Math.max(.35, Math.min(1, (viewport.clientWidth - 28) / layout.width,
      (viewport.clientHeight - 28) / layout.height)));
    viewport.scrollTo({left: 0, top: 0, behavior: "smooth"});
  }
  function selectNode(name: string) {
    setSelected(name); const next = graph?.nodes.find((item) => item.name === name);
    setContent(JSON.stringify(next?.content ?? {}, null, 2)); setError("");
  }
  function updateNode(patch: Partial<GraphNode>) {
    if (!graph) return;
    setGraph({...graph, nodes: graph.nodes.map((item) => item.name === selected ? {...item, ...patch} : item)});
  }
  function applyContent() {
    try { updateNode({content: JSON.parse(content)}); setMessage(`${selected} 节点配置已暂存`); setError(""); }
    catch (reason) { setError(`节点 content 不是合法 JSON：${reason}`); }
  }
  async function publish() {
    if (!graph || !window.confirm("确认将完整 Serving Graph 热更新到 rec-server？")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const parsed = JSON.parse(content); const assembled = {...graph, nodes: graph.nodes.map((item) => item.name === selected ? {...item, content: parsed} : item)};
      const result = await api<{version: string}>("/api/serving-graph/publish", {method: "POST", body: JSON.stringify({graph: assembled})});
      setMessage(`Serving Graph ${result.version} 已全局生效`); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Serving Graph 发布失败"); }
    finally { setBusy(false); }
  }
  async function rollback(target: string) {
    if (!window.confirm(`确认回滚并重新激活 ${target}？`)) return;
    setBusy(true); setError("");
    try { await api("/api/serving-graph/rollback", {method: "POST", body: JSON.stringify({version: target})}); setMessage(`已回滚到 ${target}`); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Serving Graph 回滚失败"); }
    finally { setBusy(false); }
  }

  return <main><header><div><p className="eyebrow">ONLINE STRATEGY</p><h1>Serving Graph</h1>
    <p className="subtitle">图形化编辑在线策略，完整校验后原子发布到 rec-server</p></div>
    <button className="refresh" onClick={() => void load()}>↻ 重新读取运行图</button></header>
    {error && <div className="notice error page-notice">{error}</div>}{message && <div className="notice success page-notice">{message}</div>}
    <section className="graph-status"><div><span>ACTIVE VERSION</span><strong>{version || "classpath-default"}</strong></div>
      <div><span>CHECKSUM</span><code>{checksum?.slice(0, 16) || "—"}</code></div><div><span>NODES / EDGES</span><strong>{graph?.nodes.length || 0} / {graph?.edges.length || 0}</strong></div></section>
    <section className="serving-layout"><div className="panel graph-panel"><div className="panel-title"><span>在线推荐执行图</span><div className="graph-tools"><small>{Math.round(zoom * 100)}%</small><button onClick={() => setZoom(Math.max(.35, zoom - .1))}>−</button><button onClick={() => setZoom(Math.min(1.8, zoom + .1))}>＋</button><button onClick={() => setZoom(1)}>1:1</button><button onClick={fitGraph}>适应窗口</button></div></div>
      <div className="graph-scroll" ref={graphViewport}>{graph && layout && <div className="graph-scale" style={{width: layout.width * zoom, height: layout.height * zoom}}><div className="graph-canvas" style={{width: layout.width, height: layout.height, transform: `scale(${zoom})`}}>
        <svg width={layout.width} height={layout.height}><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" /></marker></defs>
          {graph.edges.map((edge, index) => { const from = layout.positions.get(edge.from)!; const to = layout.positions.get(edge.to)!; const middleY = (from.y + 52 + to.y) / 2; return <path key={`${edge.from}-${edge.to}-${index}`} className="graph-edge" markerEnd="url(#arrow)" d={`M ${from.x + 66} ${from.y + 52} C ${from.x + 66} ${middleY}, ${to.x + 66} ${middleY}, ${to.x + 66} ${to.y}`} />; })}</svg>
        {graph.nodes.map((item) => { const pos = layout.positions.get(item.name)!; return <button key={item.name} style={{left: pos.x, top: pos.y}} onClick={() => selectNode(item.name)} className={`graph-node ${item.open ? "open" : "closed"} ${selected === item.name ? "selected" : ""}`}><span>{item.name}</span><small>{item.open ? "OPEN" : "CLOSED"} · {item.timeout}ms</small></button>; })}
      </div></div>}</div></div>
      <div className="panel node-editor"><div className="panel-title"><span>节点配置</span><small>{selected || "未选择"}</small></div>{node ? <div className="editor-form">
        <label>节点类<input value={node.clazz} readOnly /></label><label>配置类<input value={node.configClazz || "—"} readOnly /></label>
        <div className="editor-inline"><label className="switch-label"><input type="checkbox" checked={node.open} onChange={(event) => updateNode({open: event.target.checked})}/>启用节点</label><label>超时（ms）<input type="number" min="1" value={node.timeout} onChange={(event) => updateNode({timeout: Number(event.target.value)})}/></label></div>
        <label>content JSON<textarea spellCheck={false} value={content} onChange={(event) => setContent(event.target.value)} /></label>
        <button onClick={applyContent}>应用到草稿</button></div> : <div className="empty">请选择节点</div>}</div></section>
    <section className="panel graph-release"><div className="panel-title"><span>版本发布与回滚</span><button className="primary" disabled={!graph || busy} onClick={() => void publish()}>{busy ? "处理中…" : "校验并发布完整图"}</button></div>
      <div className="history-list">{history.length === 0 && <div className="empty">首次发布后将在此保留版本</div>}{history.map((item) => <div key={item.version}><code>{item.version}</code><span>{item.published_at ? new Date(item.published_at).toLocaleString() : "—"}</span><button disabled={busy || item.version === version} onClick={() => void rollback(item.version)}>{item.version === version ? "当前版本" : "回滚至此"}</button></div>)}</div></section>
    <footer>OpenRec Console · rec-server receives only validated full graph snapshots</footer></main>;
}

type AirflowDag = { dag_id: string; is_paused: boolean; timetable_summary?: string; description?: string };
type DagRun = { dag_run_id: string; state: string; start_date?: string };
type TaskInstance = { task_id: string; state: string; try_number?: number };
type DagTask = { task_id: string; downstream_task_ids?: string[]; operator_name?: string; [key: string]: unknown };
type DagDetail = { dag: AirflowDag & Record<string, unknown>; tasks: DagTask[]; config: unknown };
type DagConfig = {
  schedule: string; algorithms: DailyAlgorithm[]; default_revision: string;
  max_index_versions: number; retries: number; retry_delay_minutes: number;
};

const defaultDagConfig: DagConfig = {
  schedule: "0 2 * * *", algorithms: dailyAlgorithms, default_revision: "r001",
  max_index_versions: 2, retries: 1, retry_delay_minutes: 5,
};

function DagDefinition({detail, selectedTask, onSelect}: {detail: DagDetail | null; selectedTask: string; onSelect: (task: string) => void}) {
  if (!detail) return <div className="empty">正在读取 Airflow DAG 定义…</div>;
  const task = detail.tasks.find((item) => item.task_id === selectedTask);
  return <section className="dag-definition"><div className="panel-title"><span>任务定义与依赖</span><small>{detail.tasks.length} TASKS</small></div>
    <div className="dag-task-list">{detail.tasks.map((item) => <button key={item.task_id} className={selectedTask === item.task_id ? "active" : ""} onClick={() => onSelect(item.task_id)}>
      <strong>{item.task_id}</strong><small>{item.operator_name || "Airflow Task"}</small><span>→ {(item.downstream_task_ids || []).join(", ") || "END"}</span></button>)}</div>
    {task && <div className="dag-config-detail"><div><strong>任务配置 · {task.task_id}</strong><pre>{JSON.stringify(task, null, 2)}</pre></div>
      <div><strong>DAG 当前配置</strong><pre>{JSON.stringify(detail.config || detail.dag, null, 2)}</pre></div></div>}
  </section>;
}

function DagPage({mode}: {mode: "offline" | "airflow"}) {
  const [dags, setDags] = useState<AirflowDag[]>([]);
  const [selected, setSelected] = useState("openrec_daily_recall");
  const [runs, setRuns] = useState<DagRun[]>([]);
  const [tasks, setTasks] = useState<TaskInstance[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [taskLog, setTaskLog] = useState("");
  const [config, setConfig] = useState<DagConfig>(defaultDagConfig);
  const [version, setVersion] = useState<string | null>(null);
  const [history, setHistory] = useState<Array<{version: string; published_at?: string}>>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dagDetail, setDagDetail] = useState<DagDetail | null>(null);
  const [selectedTask, setSelectedTask] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      if (mode === "airflow") {
        const dagResult = await api<{dags: AirflowDag[]}>("/api/airflow/dags");
        setDags(dagResult.dags || []);
      } else {
        const configResult = await api<{version: string | null; config: DagConfig; history: Array<{version: string; published_at?: string}>}>(
          "/api/dag-configs/openrec_daily_recall");
        setConfig(configResult.config);
        setVersion(configResult.version);
        setHistory(configResult.history || []);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法加载 DAG 管控数据"); }
  }, [mode]);

  const loadRuns = useCallback(async (dagId: string) => {
    try {
      const result = await api<{dag_runs: DagRun[]}>(`/api/airflow/dags/${encodeURIComponent(dagId)}/runs`);
      setRuns(result.dag_runs || []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法加载运行记录"); }
  }, []);

  const loadDagDetail = useCallback(async (dagId: string) => {
    setDagDetail(null); setSelectedTask("");
    try {
      const result = await api<DagDetail>(`/api/airflow/dags/${encodeURIComponent(dagId)}`);
      setDagDetail(result); setSelectedTask(result.tasks[0]?.task_id || "");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法加载 DAG 定义"); }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (mode === "airflow" && selected) void loadRuns(selected); }, [mode, selected, loadRuns]);
  useEffect(() => { if (selected) void loadDagDetail(selected); }, [selected, loadDagDetail]);

  async function loadTasks(runId: string) {
    setSelectedRun(runId); setTaskLog(""); setError("");
    try {
      const result = await api<{task_instances: TaskInstance[]}>(
        `/api/airflow/dags/${encodeURIComponent(selected)}/runs/${encodeURIComponent(runId)}/tasks`);
      setTasks(result.task_instances || []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法加载 Task 状态"); }
  }

  async function loadLog(task: TaskInstance) {
    try {
      const result = await api<unknown>(`/api/airflow/dags/${encodeURIComponent(selected)}/runs/${encodeURIComponent(selectedRun)}/tasks/${encodeURIComponent(task.task_id)}/logs?try_number=${task.try_number || 1}`);
      setTaskLog(typeof result === "string" ? result : JSON.stringify(result, null, 2));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法加载 Task 日志"); }
  }

  function moveAlgorithm(algorithm: DailyAlgorithm, offset: number) {
    const items = [...config.algorithms]; const from = items.indexOf(algorithm); const to = from + offset;
    if (from < 0 || to < 0 || to >= items.length) return;
    [items[from], items[to]] = [items[to], items[from]]; setConfig({...config, algorithms: items});
  }

  async function dagAction(action: "trigger" | "pause", paused?: boolean) {
    setBusy(action); setError(""); setMessage("");
    try {
      if (action === "trigger") {
        await api(`/api/airflow/dags/${encodeURIComponent(selected)}/runs`, {
          method: "POST", body: JSON.stringify({conf: {revision: config.default_revision}}),
        });
        setMessage(`已触发 ${selected}`); await loadRuns(selected);
      } else {
        await api(`/api/airflow/dags/${encodeURIComponent(selected)}`, {
          method: "PATCH", body: JSON.stringify({is_paused: paused}),
        });
        setMessage(paused ? "DAG 已暂停" : "DAG 已启用"); await load();
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Airflow 操作失败"); }
    finally { setBusy(""); }
  }

  async function publishConfig() {
    setBusy("publish"); setError(""); setMessage("");
    try {
      const result = await api<{version: string}>("/api/dag-configs/openrec_daily_recall/publish", {
        method: "POST", body: JSON.stringify(config),
      });
      setMessage(`配置 ${result.version} 已发布，Airflow 将在下一次解析时生效`); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "配置发布失败"); }
    finally { setBusy(""); }
  }

  async function rollbackConfig() {
    if (!window.confirm("确认回滚到上一个 DAG 配置版本？")) return;
    setBusy("rollback"); setError("");
    try {
      await api("/api/dag-configs/openrec_daily_recall/rollback", {
        method: "POST", body: JSON.stringify({}),
      });
      setMessage("DAG 配置已回滚"); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "配置回滚失败"); }
    finally { setBusy(""); }
  }

  const currentDag = dags.find((dag) => dag.dag_id === selected);
  return <main>
    <header><div><p className="eyebrow">{mode === "airflow" ? "AIRFLOW CONTROL" : "OFFLINE WORKFLOW"}</p>
      <h1>{mode === "airflow" ? "Airflow 自动化" : "离线任务 DAG"}</h1>
      <p className="subtitle">{mode === "airflow" ? "观察、触发并管理 OpenRec 自动化工作流" : "配置并发布 OpenRec 离线推荐任务"}</p></div>
      <button className="refresh" onClick={() => void load()}>↻ 刷新状态</button></header>
    {error && <div className="notice error page-notice">{error}</div>}
    {message && <div className="notice success page-notice">{message}</div>}
    {mode === "airflow" && <section className="dag-layout">
      <div className="dag-list panel"><div className="panel-title"><span>DAG 列表</span><b>{dags.length}</b></div>
        {dags.map((dag) => <button key={dag.dag_id} onClick={() => setSelected(dag.dag_id)}
          className={selected === dag.dag_id ? "dag-item active" : "dag-item"}>
          <span><strong>{dag.dag_id}</strong><small>{dag.timetable_summary || "Manual"}</small></span>
          <i className={dag.is_paused ? "state paused" : "state running"}>{dag.is_paused ? "PAUSED" : "ACTIVE"}</i>
        </button>)}</div>
      <div className="panel dag-detail"><div className="panel-title"><span>{selected}</span>
        <div className="actions"><button onClick={() => void dagAction("pause", !currentDag?.is_paused)} disabled={!!busy}>
          {currentDag?.is_paused ? "启用" : "暂停"}</button><button className="primary" onClick={() => void dagAction("trigger")} disabled={!!busy}>立即运行</button></div></div>
        <p className="muted">{currentDag?.description || "OpenRec Airflow workflow"}</p>
        <DagDefinition detail={dagDetail} selectedTask={selectedTask} onSelect={setSelectedTask}/>
        <div className="run-list">{runs.length === 0 && <div className="empty">暂无运行记录</div>}
          {runs.map((run) => <button className="run" onClick={() => void loadTasks(run.dag_run_id)} key={run.dag_run_id}><code>{run.dag_run_id}</code>
            <span>{run.start_date ? new Date(run.start_date).toLocaleString() : "—"}</span>
            <i className={`run-state ${run.state}`}>{run.state}</i></button>)}</div>
        {selectedRun && <div className="task-drawer"><div className="panel-title"><span>{selectedRun}</span><small>Task instances</small></div>
          {tasks.map((task) => <button className="task-row" onClick={() => void loadLog(task)} key={task.task_id}><code>{task.task_id}</code>
            <span>try {task.try_number ?? 0}</span><i className={`run-state ${task.state}`}>{task.state || "none"}</i></button>)}
          {taskLog && <pre className="task-log">{taskLog}</pre>}</div>}
      </div>
    </section>}
    {mode === "offline" && <><section className="panel offline-dag-panel"><div className="panel-title"><span>Airflow DAG · {selected}</span><small>点击任务名查看 DAG 与配置</small></div>
      <DagDefinition detail={dagDetail} selectedTask={selectedTask} onSelect={setSelectedTask}/></section>
      <section className="panel config-panel"><div className="panel-title"><span>Daily Recall 配置</span>
      <small>当前版本 {version || "默认配置"}</small></div>
      <div className="config-grid">
        <label>调度周期 <input value={config.schedule} onChange={(e) => setConfig({...config, schedule: e.target.value})}/></label>
        <label>默认 revision <input value={config.default_revision} onChange={(e) => setConfig({...config, default_revision: e.target.value})}/></label>
        <label>索引保留数 <input type="number" min="2" max="10" value={config.max_index_versions} onChange={(e) => setConfig({...config, max_index_versions: Number(e.target.value)})}/></label>
        <label>失败重试次数 <input type="number" min="0" max="10" value={config.retries} onChange={(e) => setConfig({...config, retries: Number(e.target.value)})}/></label>
        <label>重试间隔（分钟） <input type="number" min="1" max="60" value={config.retry_delay_minutes} onChange={(e) => setConfig({...config, retry_delay_minutes: Number(e.target.value)})}/></label>
        <fieldset><legend>算法与依赖顺序</legend>{dailyAlgorithms.map((algorithm) => <div className="algorithm-order" key={algorithm}><label className="check">
          <input type="checkbox" checked={config.algorithms.includes(algorithm)} onChange={(e) => setConfig({...config,
            algorithms: e.target.checked ? [...config.algorithms, algorithm] : config.algorithms.filter((item) => item !== algorithm)})}/>{labels[algorithm]}</label>
          {config.algorithms.includes(algorithm) && <span><button type="button" onClick={() => moveAlgorithm(algorithm, -1)}>↑</button><button type="button" onClick={() => moveAlgorithm(algorithm, 1)}>↓</button></span>}</div>)}</fieldset>
      </div>
      <div className="config-actions"><span>保留 {history.length} 个配置版本</span>
        <button onClick={() => void rollbackConfig()} disabled={history.length < 2 || !!busy}>回滚配置</button>
        <button className="primary" onClick={() => void publishConfig()} disabled={!!busy}>{busy === "publish" ? "发布中…" : "校验并发布"}</button></div>
    </section></>}
    <footer>{mode === "airflow" ? "OpenRec Console · Airflow remains the execution source of truth" : "OpenRec Console · Versioned offline workflow configuration"}</footer>
  </main>;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败 (${response.status})`);
  }
  return response.json();
}

type ModelRelease = {version: string; created_at?: string;
  metrics?: {auc?: number | null; samples?: number; feature_dim?: number};
  gate?: {passed?: boolean; min_auc?: number}};
type ModelReleaseSet = {scene: string; active_version: string | null; releases: ModelRelease[]};

function ModelPage() {
  const [scene, setScene] = useState("scene_0"); const [data, setData] = useState<ModelReleaseSet | null>(null);
  const [busy, setBusy] = useState(""); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const load = useCallback(async () => { setError(""); try { setData(await api<ModelReleaseSet>(`/api/models/releases/${encodeURIComponent(scene)}`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "模型版本读取失败"); } }, [scene]);
  useEffect(() => { void load(); }, [load]);
  async function activate(version?: string) {
    const rollback = !version;
    if (!window.confirm(rollback ? "确认回滚到上一个评估通过的模型？" : `确认发布 ${version}？`)) return;
    setBusy(version || "rollback"); setError(""); setMessage("");
    try { const result = await api<ModelReleaseSet>(`/api/models/releases/${rollback ? "rollback" : "publish"}`,
      {method: "POST", body: JSON.stringify(rollback ? {scene} : {scene, version})});
      setMessage(`${rollback ? "回滚" : "发布"}成功：${result.active_version}`); setData(result); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "模型操作失败"); } finally { setBusy(""); }
  }
  return <main><header><div><p className="eyebrow">MODEL LIFECYCLE</p><h1>Rank Model</h1><p className="subtitle">训练评估产物、原子发布与保留版本回滚</p></div>
    <div className="actions"><input value={scene} onChange={(event) => setScene(event.target.value)}/><button onClick={() => void load()}>↻ 刷新</button></div></header>
    {error && <div className="notice error page-notice">{error}</div>}{message && <div className="notice success page-notice">{message}</div>}
    <section className="graph-status"><div><span>ACTIVE VERSION</span><strong>{data?.active_version || "未发布"}</strong></div><div><span>SCENE</span><code>{scene}</code></div><div><span>RETAINED</span><strong>{data?.releases.length || 0}</strong></div></section>
    <section className="panel model-releases"><div className="panel-title"><span>模型版本与评估指标</span><button disabled={!data?.active_version || !!busy} onClick={() => void activate()}>回滚上一版本</button></div>
      <div className="model-release-list">{data?.releases.map((release) => { const active = release.version === data.active_version; return <article className={active ? "active" : ""} key={release.version}>
        <div><code>{release.version}</code><small>{release.created_at ? new Date(release.created_at).toLocaleString() : "—"}</small></div><span>AUC <b>{release.metrics?.auc == null ? "N/A" : release.metrics.auc.toFixed(4)}</b></span><span>SAMPLES <b>{release.metrics?.samples ?? "—"}</b></span><span>DIM <b>{release.metrics?.feature_dim ?? "—"}</b></span>
        <em className={release.gate?.passed ? "passed" : "failed"}>{release.gate?.passed ? "GATE PASSED" : "GATE FAILED"}</em><button disabled={active || !release.gate?.passed || !!busy} onClick={() => void activate(release.version)}>{active ? "当前在线" : "发布此版本"}</button>
      </article>; })}{data?.releases.length === 0 && <div className="empty">运行 openrec_rank_model DAG 后将在此显示版本</div>}</div></section><footer>OpenRec Console · rank-engine model activation is atomic</footer></main>;
}

function shortDate(index: string) {
  const match = index.match(/-(\d{4})(\d{2})(\d{2})-(r\d+)$/);
  return match ? `${match[1]}-${match[2]}-${match[3]} · ${match[4]}` : index;
}

function App() {
  const [page, setPage] = useState<"recall" | "dag" | "airflow" | "serving" | "entities" | "monitor" | "model">("recall");
  const [selected, setSelected] = useState<Algorithm>("hot");
  const [data, setData] = useState<Record<string, ReleaseSet>>({});
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const results = await Promise.all(
        algorithms.map((algorithm) => api<ReleaseSet>(`/api/recall/releases/${algorithm}`)),
      );
      setData(Object.fromEntries(results.map((result) => [result.algorithm, result])));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法加载召回索引");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function operate(action: "switch" | "rollback", target?: string) {
    const prompt = action === "rollback"
      ? `确认将 ${labels[selected]} 回滚到上一个保留版本？`
      : `确认切换 ${labels[selected]} 到 ${target}？`;
    if (!window.confirm(prompt)) return;
    setWorking(target || action);
    setError("");
    setMessage("");
    try {
      const body = action === "switch"
        ? { algorithm: selected, target_index: target }
        : { algorithm: selected };
      const result = await api<{ index: string }>(`/api/recall/releases/${action}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMessage(`${action === "switch" ? "切换" : "回滚"}成功：${result.index}`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setWorking("");
    }
  }

  const current = data[selected];
  const active = current?.releases.find((release) => release.active);
  const previous = current?.releases.find((release) => !release.active);
  const totalIndexes = Object.values(data).reduce((sum, item) => sum + item.indexes.length, 0);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">O</span><span>OpenRec</span></div>
        <p className="eyebrow">CONTROL PLANE</p>
        <nav>
          {modules.map(([name, state, key], index) => (
            <button className={page === key ? "nav-item active" : "nav-item"}
              key={key} onClick={() => setPage(key === "dag" ? "dag" : key)}>
              <span className="nav-icon">{["⌁", "◎", "⌘", "↗", "◫", "⇢", "◇"][index]}</span>
              <span>{name}</span><small>{state}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot"><span className="pulse" /> Elasticsearch connected</div>
      </aside>

      {page === "dag" ? <DagPage mode="offline" /> : page === "airflow" ? <DagPage mode="airflow" /> : page === "serving" ? <ServingGraphPage /> : page === "entities" ? <EntityQueryPage /> : page === "monitor" ? <MonitorPage /> : page === "model" ? <ModelPage /> : <main>
        <header>
          <div><p className="eyebrow">RECALL OPERATIONS</p><h1>召回索引管理</h1>
            <p className="subtitle">查看、切换并安全回滚在线召回版本</p></div>
          <button className="refresh" onClick={() => void load()} disabled={loading}>↻ 刷新状态</button>
        </header>

        <section className="metrics">
          <article><span>召回通道</span><strong>3</strong><small>HOT · NEW · I2I</small></article>
          <article><span>已加载索引</span><strong>{loading ? "—" : totalIndexes}</strong><small>跨全部召回通道</small></article>
          <article><span>版本保留策略</span><strong>2</strong><small>在线版本 + 回滚版本</small></article>
        </section>

        <section className="workspace">
          <div className="tabs">
            {algorithms.map((algorithm) => (
              <button key={algorithm} onClick={() => setSelected(algorithm)}
                className={selected === algorithm ? "tab active" : "tab"}>
                <span>{labels[algorithm]}</span><code>{algorithm}</code>
              </button>
            ))}
          </div>

          {error && <div className="notice error">{error}</div>}
          {message && <div className="notice success">{message}</div>}

          <div className="section-head">
            <div><h2>{labels[selected]}</h2><p>物理索引按业务日期与修订版本排列</p></div>
            <button className="rollback" disabled={!previous || !!working}
              onClick={() => void operate("rollback")}>↶ 回滚上一版本</button>
          </div>

          <div className="release-list">
            {loading && <div className="empty">正在同步 Elasticsearch 状态…</div>}
            {!loading && !current?.releases.length && <div className="empty">当前没有可用索引</div>}
            {current?.releases.map((release) => (
              <article className={release.active ? "release active" : "release"} key={release.index}>
                <div className="version-line"><span className="database">◆</span><div>
                  <h3>{release.index}</h3><p>{shortDate(release.index)}</p></div></div>
                <div className="documents"><strong>{release.documents.toLocaleString()}</strong><span>documents</span></div>
                <div className={release.active ? "badge online" : "badge standby"}>
                  <span />{release.active ? "ONLINE" : "STANDBY"}
                </div>
                {release.active ? <span className="current">当前生效</span> :
                  <button className="switch" disabled={!!working}
                    onClick={() => void operate("switch", release.index)}>
                    {working === release.index ? "切换中…" : "切换至此版本"}
                  </button>}
              </article>
            ))}
          </div>

          {active && <div className="alias"><span>ACTIVE ALIAS</span><code>openrec-recall-{selected}-active</code>
            <b>→</b><code>{active.index}</code></div>}
        </section>
        <footer>OpenRec Console · Internal control plane · 操作将直接影响在线召回流量</footer>
      </main>}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);

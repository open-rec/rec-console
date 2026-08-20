import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Algorithm = "hot" | "new" | "i2i";
type Release = { index: string; active: boolean; documents: number };
type ReleaseSet = {
  algorithm: Algorithm;
  active_indexes: string[];
  indexes: string[];
  releases: Release[];
};

const algorithms: Algorithm[] = ["hot", "new", "i2i"];
const labels: Record<Algorithm, string> = {
  hot: "热门召回",
  new: "新品召回",
  i2i: "I2I 召回",
};

const modules = [
  ["召回索引", "已启用", "recall"],
  ["推荐链路 DAG", "规划中", "dag"],
  ["监控大盘", "规划中", "monitor"],
  ["Airflow 自动化", "规划中", "airflow"],
  ["Rank Model", "规划中", "model"],
] as const;

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

function shortDate(index: string) {
  const match = index.match(/-(\d{4})(\d{2})(\d{2})-(r\d+)$/);
  return match ? `${match[1]}-${match[2]}-${match[3]} · ${match[4]}` : index;
}

function App() {
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
            <button className={index === 0 ? "nav-item active" : "nav-item"} key={key} disabled={index !== 0}>
              <span className="nav-icon">{["⌁", "⌘", "◫", "↗", "◇"][index]}</span>
              <span>{name}</span><small>{state}</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot"><span className="pulse" /> Elasticsearch connected</div>
      </aside>

      <main>
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
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);

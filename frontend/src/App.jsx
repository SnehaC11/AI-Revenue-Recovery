import { useEffect, useState } from "react";
import axios from "axios";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  DollarSign,
  Filter,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  X,
  XCircle,
} from "lucide-react";
import "./App.css";

const API = "http://127.0.0.1:8000";
const terminalStatuses = new Set([
  "RECOVERED",
  "ESCALATED",
  "STOPPED",
  "POLICY_BLOCKED",
]);
const label = (value) => (value || "AI_ANALYSIS").replaceAll("_", " ");
const money = (value) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value || 0);
function decisionFor(item) {
  const source = item.agent_reason || item.reason;
  let payload = {};
  if (typeof source === "object" && source) payload = source;
  if (typeof source === "string") {
    try {
      payload = JSON.parse(source);
    } catch {
      payload = {};
    }
  }
  return {
    action: item.selected_action || payload.action || "AI_ANALYSIS",
    reason:
      payload.reason ||
      (typeof source === "string"
        ? source
        : "This case is waiting for a bounded AI decision."),
    confidence: Number(payload.confidence),
  };
}
function auditSummary(event) {
  let details = event.details || {};
  if (typeof details === "string") {
    try {
      details = JSON.parse(details);
    } catch {
      return details;
    }
  }
  const action = label(details.action);
  const type = label(details.recovery_type);
  const amount = details.amount_at_risk ? money(details.amount_at_risk) : "";
  const eventType = event.event || event.event_type;
  if (eventType === "CASE_DETECTED")
    return `${type} detected${amount ? ` with ${amount} at risk` : ""}.`;
  if (eventType === "AI_DECISION")
    return `Recommended ${action}${details.confidence ? ` with ${Math.round(details.confidence * 100)}% confidence` : ""}. ${details.reason || ""}`;
  if (eventType === "POLICY_CHECK")
    return details.allowed
      ? `Policy approved ${action}.`
      : `Policy blocked ${action}. ${details.reason || ""}`;
  if (eventType === "RECOVERY_ACTION")
    return `Started ${action}${amount ? ` for ${amount}` : ""}.`;
  if (eventType === "RECOVERY_RESULT")
    return `${label(details.status)} outcome recorded${details.amount_recovered ? ` with ${money(details.amount_recovered)} ${details.recovery_mode === "SIMULATED" ? "simulated" : "confirmed"} recovery` : ""}.`;
  if (eventType === "WORKFLOW_STOPPED")
    return `Workflow stopped: ${label(details.reason)}.`;
  return Object.entries(details)
    .map(([key, value]) => `${label(key)}: ${value}`)
    .join(". ");
}

export default function App() {
  const [metrics, setMetrics] = useState({
    revenue_at_risk: 0,
    revenue_recovered: 0,
    simulated_revenue_recovered: 0,
    confirmed_revenue_recovered: 0,
    expected_recovery: 0,
    recovery_rate: 0,
    total_cases: 0,
    recovered_cases: 0,
    escalated_cases: 0,
    stopped_cases: 0,
    active_cases: 0,
  });
  const [cases, setCases] = useState([]);
  const [feed, setFeed] = useState([]);
  const [selected, setSelected] = useState(null);
  const [events, setEvents] = useState([]);
  const [auditIntegrity, setAuditIntegrity] = useState(null);
  const [view, setView] = useState("overview");
  const [history, setHistory] = useState([]);
  const [filter, setFilter] = useState("ALL");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState("");
  const [batch, setBatch] = useState(null);

  async function refresh() {
    try {
      setLoading(true);
      const [m, c, f] = await Promise.all([
        axios.get(`${API}/analytics/revenue`),
        axios.get(`${API}/recovery/cases`),
        axios.get(`${API}/recovery/risk-feed`),
      ]);
      setMetrics(m.data);
      setCases(Array.isArray(c.data) ? c.data : c.data.cases || []);
      setFeed(Array.isArray(f.data) ? f.data : []);
    } catch {
      setNotice(
        "The recovery engine is unavailable. Start the backend and refresh.",
      );
    } finally {
      setLoading(false);
    }
  }
  async function openCase(item) {
    setSelected(item);
    try {
      const response = await axios.get(`${API}/recovery/audit/${item.case_id}`);
      setEvents(response.data.events || []);
      setAuditIntegrity(response.data.integrity || null);
    } catch {
      setEvents([]);
      setAuditIntegrity(null);
    }
  }
  async function detectRisk() {
    try {
      setRunning(true);
      setNotice("Detecting new payment revenue risk...");
      const payments = await axios.post(`${API}/recovery/detect`);
      setNotice(
        `Detection complete: ${payments.data.cases_created || 0} new payment cases available.`,
      );
      await refresh();
    } catch {
      setNotice("Risk detection could not run. Check that the backend is online.");
    } finally {
      setRunning(false);
    }
  }
  async function runBatch() {
    try {
      setRunning(true);
      setNotice("AI recovery is reviewing the active queue...");
      const response = await axios.post(`${API}/recovery/batch/execute`);
      setBatch(response.data);
      setNotice(
        response.data.cases_processed
          ? `Batch complete: ${response.data.cases_processed} cases evaluated.`
          : "No actionable cases remain in the queue.",
      );
      await refresh();
    } catch {
      setNotice("The batch could not run. Check that the backend is online.");
    } finally {
      setRunning(false);
    }
  }
  async function execute(caseId) {
    try {
      setNotice(`Running recovery workflow for ${caseId}...`);
      await axios.post(
        `${API}/recovery/cases/${caseId}/execute`,
      );
      await refresh();
      const detailResponse = await axios.get(`${API}/recovery/${caseId}`);
      await openCase(detailResponse.data);
      setNotice(`Recovery workflow completed for ${caseId}.`);
    } catch {
      setNotice(`Unable to execute ${caseId}. Check the backend response.`);
    }
  }
  function chooseView(next) {
    if (next === view) return;
    setHistory((previous) => [...previous, view]);
    setView(next);
    if (next === "overview") setFilter("ALL");
  }
  function goBack() {
    const previous = history[history.length - 1] || "overview";
    setHistory((items) => items.slice(0, -1));
    setView(previous);
  }
  function filterCases(next) {
    setFilter(next);
    chooseView("cases");
  }
  useEffect(() => {
    refresh();
  }, []);

  const filtered = cases.filter(
    (item) =>
      (filter === "ALL" ||
        (filter === "ACTIVE" && !terminalStatuses.has(item.status)) ||
        item.status === filter) &&
      (!query ||
        [
          item.case_id,
          item.customer_id,
          item.recovery_type,
          item.selected_action,
        ].some((x) =>
          String(x || "")
            .toLowerCase()
            .includes(query.toLowerCase()),
        )),
  );
  const active = cases.filter((item) => !terminalStatuses.has(item.status));
  const rate = Math.min(Number(metrics.recovery_rate || 0), 100);
  const top = [...feed]
    .sort((a, b) => (b.amount_at_risk || 0) - (a.amount_at_risk || 0))
    .slice(0, 4);
  const decisions = cases.filter(
    (item) => item.selected_action || item.agent_reason,
  );
  if (loading && !cases.length)
    return (
      <div className="loading">
        <i />
        <h1>RecoverAI</h1>
        <p>Connecting to the recovery engine...</p>
      </div>
    );

  return (
    <div className="shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => chooseView("overview")}>
          <b>
            <Activity size={21} />
          </b>
          <span>
            <strong>RecoverAI</strong>
            <small>Revenue operations</small>
          </span>
        </button>
        <nav>
          <Nav
            active={view === "overview"}
            icon={<Activity />}
            text="Overview"
            click={() => chooseView("overview")}
          />
          <Nav
            active={view === "cases"}
            icon={<AlertTriangle />}
            text="Recovery cases"
            count={active.length}
            click={() => chooseView("cases")}
          />
          <Nav
            active={view === "decisions"}
            icon={<Bot />}
            text="AI decisions"
            click={() => chooseView("decisions")}
          />
          <Nav
            active={view === "audit"}
            icon={<ShieldCheck />}
            text="Audit trail"
            click={() => chooseView("audit")}
          />
        </nav>
        <div className="side-bottom">
          <div className="agent">
            <i />
            <span>
              <strong>Agent online</strong>
              <small>Policy protected</small>
            </span>
          </div>
          <button onClick={refresh} disabled={loading || running}>
            <RefreshCw size={15} className={loading ? "spin" : ""} /> Sync live
            data
          </button>
        </div>
      </aside>
      <main>
        <header>
          <div className="title-cluster">
            {view !== "overview" && (
              <button className="back-button" onClick={goBack}>
                <ArrowLeft size={16} /> Back
              </button>
            )}
            <div>
              <p className="eyebrow">RECOVERY OPERATIONS / LIVE</p>
              <h1>
                {
                  {
                    overview: "Recovery command center",
                    cases: "Recovery case workspace",
                    decisions: "AI decision ledger",
                    audit: "Audit trail explorer",
                  }[view]
                }
              </h1>
            </div>
          </div>
          <div className="head-actions">
            <span className="healthy">
              <i /> System healthy
            </span>
            <button
              className="secondary"
              onClick={refresh}
              disabled={loading || running}
            >
              <RefreshCw size={16} className={loading ? "spin" : ""} /> Refresh
            </button>
          </div>
        </header>
        {notice && (
          <div className="notice">
            <Activity size={17} />
            {notice}
            <button onClick={() => setNotice("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {view === "overview" && (
          <>
            <section className="hero">
              <div>
                <span>
                  <Sparkles size={15} /> Bounded AI recovery
                </span>
                <h2>Move risky revenue into a protected recovery workflow.</h2>
                <p>
                  Every action is checked against policy, retry limits, and an
                  audit trail before it is executed.
                </p>
                <div className="hero-actions">
                  <button
                    className="primary"
                    onClick={runBatch}
                    disabled={running}
                  >
                    {running ? (
                      <>
                        <RefreshCw size={17} className="spin" /> Reviewing queue
                      </>
                    ) : (
                      <>
                        <Play size={17} fill="currentColor" /> Run recovery
                        batch
                      </>
                    )}
                  </button>
                  <button
                    className="secondary"
                    onClick={detectRisk}
                    disabled={running}
                  >
                    <Search size={16} /> Detect new risk
                  </button>
                  <button
                    className="hero-link"
                    onClick={() => filterCases("ACTIVE")}
                  >
                    Review active cases <ChevronRight size={16} />
                  </button>
                </div>
              </div>
              <div className="ring">
                <div>
                  <strong>{rate.toFixed(1)}%</strong>
                  <small>demo recovery</small>
                </div>
                <em>Recovery rate</em>
              </div>
            </section>
            <section className="metrics">
              <Metric
                title="Revenue at risk"
                value={money(metrics.revenue_at_risk)}
                text="Open exposure"
                icon={<AlertTriangle />}
                tone="amber"
                click={() => filterCases("ACTIVE")}
              />
              <Metric
                title="Simulated recovered"
                value={money(metrics.simulated_revenue_recovered)}
                text={`${metrics.recovered_cases || 0} demo-settled cases`}
                icon={<DollarSign />}
                tone="green"
                click={() => filterCases("RECOVERED")}
              />
              <Metric
                title="Live confirmed"
                value={money(metrics.confirmed_revenue_recovered)}
                text="Provider-settlement callbacks"
                icon={<CheckCircle2 />}
                tone="green"
                click={() => filterCases("RECOVERED")}
              />
              <Metric
                title="Active queue"
                value={metrics.active_cases || 0}
                text="Needs a decision"
                icon={<Clock3 />}
                tone="blue"
                click={() => filterCases("ACTIVE")}
              />
              <Metric
                title="Escalations"
                value={metrics.escalated_cases || 0}
                text="Safely routed for review"
                icon={<ShieldCheck />}
                tone="violet"
                click={() => filterCases("ESCALATED")}
              />
            </section>
            <section className="journey panel">
              <div>
                <p className="eyebrow">HOW RECOVERAI WORKS</p>
                <h2>From revenue signal to accountable outcome.</h2>
              </div>
              <button onClick={() => filterCases("ACTIVE")}>
                <b>01</b>
                <span>
                  <strong>Detect</strong>
                  <small>
                    {metrics.active_cases || 0} cases need attention
                  </small>
                </span>
                <ChevronRight size={17} />
              </button>
              <button onClick={() => chooseView("decisions")}>
                <b>02</b>
                <span>
                  <strong>Decide</strong>
                  <small>AI action checked by policy</small>
                </span>
                <ChevronRight size={17} />
              </button>
              <button onClick={() => chooseView("audit")}>
                <b>03</b>
                <span>
                  <strong>Prove</strong>
                  <small>Every outcome is auditable</small>
                </span>
                <ChevronRight size={17} />
              </button>
            </section>
            <section className="two-col">
              <div className="panel funnel">
                <Heading
                  eye="RECOVERY PERFORMANCE"
                  title="Revenue recovery funnel"
                  right={`${rate.toFixed(1)}% recovered`}
                />
                <div className="track">
                  <i style={{ width: `${rate}%` }} />
                </div>
                <div className="stats">
                  <Stat text="At risk" value={money(metrics.revenue_at_risk)} />
                  <Stat
                    text="Expected"
                    value={money(metrics.expected_recovery)}
                  />
                  <Stat
                    text="Simulated"
                    value={money(metrics.simulated_revenue_recovered)}
                  />
                </div>
                <div className="safe">
                  <ShieldCheck size={18} />
                  Demo settlements are explicitly simulated; production totals require provider confirmation.
                </div>
              </div>
              <div className="panel safeguards">
                <Heading eye="SAFETY LAYER" title="Guardrails online" />
                <p>
                  <CheckCircle2 /> Structured AI decisions
                </p>
                <p>
                  <CheckCircle2 /> Duplicate execution protection
                </p>
                <p>
                  <CheckCircle2 /> Tamper-evident audit events
                </p>
                <button onClick={() => filterCases("ALL")}>
                  Review recovery cases <ChevronRight size={15} />
                </button>
              </div>
            </section>
            <section className="panel opportunities">
              <Heading
                eye="PRIORITY QUEUE"
                title="Highest value opportunities"
                right="Click a case to inspect"
              />
              {top.length ? (
                top.map((item) => (
                  <button
                    className="opportunity"
                    key={item.case_id}
                    onClick={() => {
                      openCase(item);
                      chooseView("cases");
                    }}
                  >
                    <b>
                      {(item.recovery_type || item.type) ===
                      "CHECKOUT_ABANDONMENT" ? (
                        <ArrowUpRight size={17} />
                      ) : (
                        <AlertTriangle size={17} />
                      )}
                    </b>
                    <span>
                      <strong>{item.case_id}</strong>
                      <small>{label(item.recovery_type || item.type)}</small>
                    </span>
                    <span className="amount">
                      <small>AT RISK</small>
                      <strong>{money(item.amount_at_risk)}</strong>
                    </span>
                    <em>{Math.round((item.risk_score || 0) * 100)}%</em>
                    <ChevronRight size={18} />
                  </button>
                ))
              ) : (
                <Empty
                  title="No opportunities detected"
                  text="Your recovery queue is clear."
                />
              )}
            </section>
            {batch && (
              <section className="batch">
                <div>
                  <span>
                    <CheckCircle2 size={15} /> Latest batch
                  </span>
                  <h3>
                    {batch.cases_processed
                      ? "Recovery batch complete"
                      : "Queue already complete"}
                  </h3>
                </div>
                <div className="batch-stats">
                  <Stat text="Reviewed" value={batch.cases_processed} />
                  <Stat text="Recovered" value={batch.recovered_cases} />
                  <Stat text="Escalated" value={batch.escalated_cases} />
                  <Stat text="Stopped" value={batch.stopped_cases} />
                  <Stat text="Blocked" value={batch.blocked_cases} />
                </div>
              </section>
            )}
          </>
        )}
        {view === "cases" && (
          <section className="case-layout">
            <div className="panel queue">
              <Heading
                eye="RECOVERY QUEUE"
                title={`${filtered.length} matching cases`}
              />
              <div className="tools">
                <label>
                  <Search size={16} />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search case, customer or action"
                  />
                </label>
                <label>
                  <Filter size={15} />
                  <select
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option value="ALL">All statuses</option>
                    <option value="ACTIVE">Active</option>
                    <option value="AT_RISK">At risk</option>
                    <option value="RECOVERED">Recovered</option>
                    <option value="ESCALATED">Escalated</option>
                    <option value="STOPPED">Stopped</option>
                    <option value="POLICY_BLOCKED">Policy blocked</option>
                  </select>
                </label>
              </div>
              <div className="case-list">
                {filtered.length ? (
                  filtered.map((item) => (
                    <CaseRow
                      item={item}
                      selected={selected?.case_id === item.case_id}
                      key={item.case_id}
                      click={() => openCase(item)}
                    />
                  ))
                ) : (
                  <Empty
                    title="No matching cases"
                    text="Try a different filter or search term."
                  />
                )}
              </div>
            </div>
              <Inspector
                item={selected}
                events={events}
                integrity={auditIntegrity}
                close={() => {
                  setSelected(null);
                  setEvents([]);
                  setAuditIntegrity(null);
                }}
              execute={execute}
            />
          </section>
        )}
        {view === "decisions" && (
          <section className="panel decisions">
            <Heading
              eye="AI DECISION LEDGER"
              title="Decisions with evidence"
              right={`${decisions.length} available`}
            />
            {decisions.length ? (
              decisions.map((item) => (
                <button
                  key={item.case_id}
                  onClick={() => {
                    openCase(item);
                    chooseView("cases");
                  }}
                >
                  <b>
                    <Bot size={17} />
                  </b>
                  <span>
                    <strong>{label(decisionFor(item).action)}</strong>
                    <small>{decisionFor(item).reason}</small>
                  </span>
                  <Badge status={item.status} />
                  <ChevronRight size={18} />
                </button>
              ))
            ) : (
              <Empty
                title="No decisions yet"
                text="Run a recovery batch to generate decision records."
              />
            )}
          </section>
        )}
        {view === "audit" && (
          <section className="audit-layout">
            <div className="panel picker">
              <Heading eye="AUDIT EXPLORER" title="Select a case" />
              {cases.slice(0, 8).map((item) => (
                <button
                  key={item.case_id}
                  className={selected?.case_id === item.case_id ? "chosen" : ""}
                  onClick={() => openCase(item)}
                >
                  {item.case_id}
                  <Badge status={item.status} />
                </button>
              ))}
            </div>
            <div className="panel audit">
              <Heading
                eye="EVENT HISTORY"
                title={selected ? selected.case_id : "Choose a case"}
              />
              {selected ? (
                <Timeline events={events} />
              ) : (
                <Empty
                  title="No case selected"
                  text="Choose a recovery case to review its audit history."
                />
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function Nav({ active, icon, text, count, click }) {
  return (
    <button className={active ? "nav active" : "nav"} onClick={click}>
      {icon}
      <span>{text}</span>
      {count !== undefined && <b>{count}</b>}
    </button>
  );
}
function Heading({ eye, title, right }) {
  return (
    <div className="heading">
      <div>
        <p className="eyebrow">{eye}</p>
        <h2>{title}</h2>
      </div>
      {right && <small>{right}</small>}
    </div>
  );
}
function Stat({ text, value }) {
  return (
    <div className="stat">
      <small>{text}</small>
      <strong>{value}</strong>
    </div>
  );
}
function Metric({ title, value, text, icon, tone, click }) {
  return (
    <button className={`metric ${tone}`} onClick={click}>
      <b>{icon}</b>
      <span>
        <small>{title}</small>
        <strong>{value}</strong>
        <em>{text}</em>
      </span>
      <ChevronRight size={17} />
    </button>
  );
}
function Badge({ status }) {
  const s = (status || "AT_RISK").toUpperCase();
  const Icon =
    s === "RECOVERED"
      ? CheckCircle2
      : s === "ESCALATED"
        ? AlertTriangle
        : terminalStatuses.has(s)
          ? XCircle
          : Clock3;
  return (
    <span className={`badge ${s.toLowerCase()}`}>
      <Icon size={13} />
      {label(s)}
    </span>
  );
}
function Empty({ title, text }) {
  return (
    <div className="empty">
      <CheckCircle2 size={28} />
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}
function CaseRow({ item, selected, click }) {
  return (
    <button
      className={selected ? "case-row selected" : "case-row"}
      onClick={click}
    >
      <b>
        {item.recovery_type === "CHECKOUT_ABANDONMENT" ? (
          <ArrowUpRight size={16} />
        ) : (
          <AlertTriangle size={16} />
        )}
      </b>
      <span>
        <strong>{item.case_id}</strong>
        <small>
          {item.customer_id} / {label(item.recovery_type)}
        </small>
      </span>
      <em>
        <small>AT RISK</small>
        <strong>{money(item.amount_at_risk)}</strong>
      </em>
      <Badge status={item.status} />
      <ChevronRight size={17} />
    </button>
  );
}
function Inspector({ item, events, integrity, close, execute }) {
  if (!item)
    return (
      <aside className="panel inspector empty-inspector">
        <Bot size={30} />
        <h3>Select a recovery case</h3>
        <p>
          Click any item in the queue to inspect its AI decision, outcomes, and
          audit events.
        </p>
      </aside>
    );
  const recoveryType = item.recovery_type || item.type;
  const canRun = item.status === "AT_RISK" || item.status === "OPEN";
  const decision = decisionFor(item);
  const confidence = Number.isFinite(decision.confidence)
    ? `${Math.round(decision.confidence * 100)}% confidence`
    : "Policy checked";
  return (
    <aside className="panel inspector">
      <div className="inspector-head">
        <div>
          <p className="eyebrow">CASE INSPECTOR</p>
          <h3>{item.case_id}</h3>
        </div>
        <button onClick={close}>
          <X size={18} />
        </button>
      </div>
      <div className="risk-total">
        <small>REVENUE AT RISK</small>
        <strong>{money(item.amount_at_risk)}</strong>
        <Badge status={item.status} />
      </div>
      <div className="decision-card">
        <div>
          <span>AI RECOMMENDATION</span>
          <strong>{label(decision.action)}</strong>
        </div>
        <em>{confidence}</em>
        <p>{decision.reason}</p>
      </div>
      <div className="inspect-grid">
        <Stat text="Recovery type" value={label(recoveryType)} />
        <Stat
          text="Risk score"
          value={`${Math.round((item.risk_score || 0) * 100)}%`}
        />
        <Stat text="Expected recovery" value={money(item.expected_recovery)} />
        <Stat text="Recovered" value={money(item.amount_recovered)} />
      </div>
      {canRun && (
        <button className="primary full" onClick={() => execute(item.case_id)}>
          <Play size={16} fill="currentColor" /> Execute recovery workflow
        </button>
      )}
      <div className="mini-audit">
        <strong>
          <ShieldCheck size={16} /> Audit events
        </strong>
        {integrity && (
          <small className={integrity.valid ? "audit-valid" : "audit-invalid"}>
            {integrity.valid
              ? `Integrity verified · ${integrity.events_verified} events`
              : "Integrity check failed"}
          </small>
        )}
        <Timeline events={events} compact />
      </div>
    </aside>
  );
}
function Timeline({ events, compact }) {
  if (!events.length)
    return (
      <Empty
        title="No audit events yet"
        text="Events appear after the workflow evaluates this case."
      />
    );
  return (
    <div className={compact ? "timeline compact" : "timeline"}>
      {events.map((event, index) => (
        <div key={`${event.event || event.event_type}-${index}`}>
          <b>
            <CheckCircle2 size={13} />
          </b>
          <span>
            <strong>{label(event.event || event.event_type)}</strong>
            <p>{auditSummary(event)}</p>
            <small>{event.created_at || event.timestamp || "Recorded"}</small>
          </span>
        </div>
      ))}
    </div>
  );
}

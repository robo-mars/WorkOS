import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUp,
  Bell,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  LayoutGrid,
  Loader2,
  MapPin,
  MessageSquare,
  Monitor,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Ticket,
  Users,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "./api";
import type { Run, Resource } from "./api";
type Page =
  | "Assistant"
  | "My workflows"
  | "Spaces"
  | "IT support"
  | "Knowledge"
  | "People"
  | "Preferences";
const nav: { label: Page; icon: LucideIcon }[] = [
  { label: "Assistant", icon: Sparkles },
  { label: "My workflows", icon: LayoutGrid },
  { label: "Spaces", icon: MapPin },
  { label: "IT support", icon: Ticket },
  { label: "Knowledge", icon: BookOpen },
  { label: "People", icon: Users },
];
const prompts = [
  {
    title: "Find my focus space",
    description: "Book a desk that works for you",
    icon: MapPin,
    color: "green",
    text: "Book me a desk near Engineering in Dubai tomorrow.",
  },
  {
    title: "Get a little IT help",
    description: "Equipment, access, or a quick fix",
    icon: Monitor,
    color: "blue",
    text: "Create an IT ticket for a monitor.",
  },
  {
    title: "Find the right answer",
    description: "Policies, onboarding, and more",
    icon: BookOpen,
    color: "orange",
    text: "What are the onboarding requirements?",
  },
  {
    title: "Meet your people",
    description: "Find a teammate or an expert",
    icon: Users,
    color: "purple",
    text: "Find the Engineering team.",
  },
];
const pretty = (s: string) =>
  s.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status}>
      <span />
      {pretty(status)}
    </span>
  );
}
function App() {
  const [page, setPage] = useState<Page>("Assistant"),
    [ready, setReady] = useState(false),
    [code, setCode] = useState("workplace-demo"),
    [login, setLogin] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]),
    [active, setActive] = useState<Run | null>(null),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [resources, setResources] = useState<Record<string, Resource[]>>({
      reservation: [],
      ticket: [],
      access: [],
    }),
    [preferences, setPreferences] = useState({
      building: "Dubai",
      zone: "Engineering",
    }),
    [saved, setSaved] = useState(false),
    [tools, setTools] = useState<Record<string, unknown>>({}),
    [showActivity, setShowActivity] = useState(false),
    [audit, setAudit] = useState<
      { id: string; event: string; at: string; tool?: string }[]
    >([]);
  const [conversation, setConversation] = useState<string | undefined>();
  const requestKey = useRef<{ text: string; id: string } | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null),
    bottom = useRef<HTMLDivElement>(null);
  async function refresh() {
    const [r, res, p, a] = await Promise.all([
      api<Run[]>("/runs"),
      api<Record<string, Resource[]>>("/resources"),
      api<typeof preferences>("/preferences"),
      api<typeof audit>("/audit"),
    ]);
    setRuns(r);
    setResources(res);
    if (p.building) setPreferences(p);
    setAudit(a);
  }
  useEffect(() => {
    api("/session")
      .then(() => {
        setReady(true);
        return refresh();
      })
      .catch(() => setLogin(true));
  }, []);
  useEffect(() => {
    if (ready)
      api<Record<string, unknown>>("/tools")
        .then(setTools)
        .catch(() => {});
  }, [ready]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active, busy]);
  async function signIn() {
    setError("");
    try {
      await api("/session", { method: "POST", body: JSON.stringify({ code }) });
      setReady(true);
      setLogin(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function send(text = input) {
    if (busy || text.trim().length < 3) return;
    setError("");
    setBusy(true);
    setPage("Assistant");
    setInput("");
    try {
      if (!requestKey.current || requestKey.current.text !== text)
        requestKey.current = { text, id: crypto.randomUUID() };
      const run = await api<Run>("/runs", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          conversation_id: conversation,
          request_id: requestKey.current.id,
        }),
      });
      setActive(run);
      setConversation(run.conversation_id);
      requestKey.current = null;
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      setInput(text);
    } finally {
      setBusy(false);
    }
  }
  async function decide(approved: boolean) {
    if (!active || busy) return;
    setBusy(true);
    setError("");
    try {
      setActive(
        await api<Run>("/runs/" + active.id + "/approval", {
          method: "POST",
          body: JSON.stringify({ approved }),
        }),
      );
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function openRun(run: Run) {
    setActive(run);
    setConversation(run.conversation_id);
    setPage("Assistant");
  }
  function newChat() {
    requestKey.current = null;
    setActive(null);
    setConversation(undefined);
    setPage("Assistant");
    setInput("");
    inputRef.current?.focus();
  }
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        newChat();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  const pending = runs.filter((r) => r.status === "awaiting_approval").length;
  const currentRuns = active
    ? runs.filter((r) => r.conversation_id === active.conversation_id).reverse()
    : [];
  const confirmed =
    resources.reservation?.filter((r) => r.status === "confirmed") || [];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            newChat();
          }}
        >
          <span className="brand-symbol">
            <span />
            <span />
            <span />
            <span />
          </span>
          workplace<span className="brand-os">OS</span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">W</span>
          <div>
            <strong>Acme workspace</strong>
            <small>Employee workspace</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <button className="new-chat" onClick={newChat}>
          <Plus size={17} /> New conversation <span>⌘ K</span>
        </button>
        <p className="nav-caption">YOUR WORKPLACE</p>
        <nav>
          {nav.map(({ label, icon: Icon }) => (
            <button
              key={label}
              className={page === label ? "selected" : ""}
              onClick={() => setPage(label)}
            >
              <Icon size={18} />
              {label}
              {label === "My workflows" && pending > 0 ? (
                <span className="nav-count">{pending}</span>
              ) : null}
              {label === "Assistant" && <span className="new-label">NEW</span>}
            </button>
          ))}
        </nav>
        <div className="recent">
          <p className="nav-caption">RECENT CONVERSATIONS</p>
          {runs.slice(0, 4).map((run) => (
            <button key={run.id} onClick={() => openRun(run)}>
              <MessageSquare size={14} />
              <span>{run.user_request}</span>
            </button>
          ))}
          {runs.length === 0 && (
            <p className="quiet-text">
              A fresh start. Your conversations
              <br />
              will appear here.
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="connected-note">
            <span className="pulse-dot" />
            <strong>Your workplace, connected</strong>
            <p>Less switching. More doing.</p>
          </div>
          <button
            className={
              "preferences " + (page === "Preferences" ? "selected" : "")
            }
            onClick={() => setPage("Preferences")}
          >
            <Settings2 size={17} />
            Preferences
          </button>
          <div className="profile">
            <span className="avatar">MH</span>
            <div>
              <strong>Mariam Hashmi</strong>
              <small>Engineering · Dubai</small>
            </div>
            <button
              aria-label="Sign out"
              title="Sign out"
              onClick={async () => {
                await api("/session", { method: "DELETE" });
                setReady(false);
                setLogin(true);
                setRuns([]);
                setActive(null);
              }}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="crumb">Workspace</span>
            <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <span className="office">
              <span />
              Dubai office <ChevronDown size={12} />
            </span>
            <span className="divider" />
            <button
              aria-label="View activity"
              className="notification"
              onClick={() => setShowActivity(!showActivity)}
            >
              <Bell size={18} />
              {pending > 0 && <i />}
            </button>
            <span className="mini-avatar">MH</span>
          </div>
        </header>
        <main>
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {page === "Assistant" && (
            <div
              className={"assistant-page " + (active ? "has-conversation" : "")}
            >
              {!active && !busy ? (
                <>
                  <div className="intro">
                    <div className="eyebrow">
                      <span className="tiny-spark">
                        <Sparkles size={14} />
                      </span>{" "}
                      A LITTLE LESS ADMIN. A LITTLE MORE POSSIBILITY.
                    </div>
                    <h1>
                      Your workday,
                      <br />
                      <span>working together.</span>
                    </h1>
                    <p>
                      Find a space. Get support. Make your next move.
                      <br />
                      One conversation connects it all.
                    </p>
                  </div>
                  <div className="prompt-grid">
                    {prompts.map(
                      ({ title, description, icon: Icon, color, text }) => (
                        <button
                          className="prompt-card"
                          key={title}
                          onClick={() => send(text)}
                          disabled={!ready}
                        >
                          <div className={"prompt-icon " + color}>
                            <Icon size={20} />
                          </div>
                          <ArrowRight className="card-arrow" size={17} />
                          <h3>{title}</h3>
                          <p>{description}</p>
                        </button>
                      ),
                    )}
                  </div>
                  <button
                    className="onboarding-banner"
                    onClick={() =>
                      send(
                        "I start Monday in Dubai. Book me a desk near Engineering, check onboarding requirements, and create an IT ticket for a monitor.",
                      )
                    }
                    disabled={!ready}
                  >
                    <div className="banner-icon">
                      <Zap size={21} />
                    </div>
                    <div>
                      <span>BIG PLANS? START SMALL.</span>
                      <h3>First day? Let’s get you settled in.</h3>
                      <p>
                        A desk, your equipment, and the essentials. All in one
                        go.
                      </p>
                    </div>
                    <span className="try-workflow">
                      Try a workflow <ArrowRight size={15} />
                    </span>
                  </button>
                </>
              ) : (
                <div className="conversation">
                  <div className="conversation-heading">
                    <div>
                      <span className="eyebrow">YOUR WORKPLACE ASSISTANT</span>
                      <h1>Let’s make it happen.</h1>
                    </div>
                    <button className="text-button" onClick={newChat}>
                      <Plus size={15} />
                      New conversation
                    </button>
                  </div>
                  {currentRuns.map((run) => (
                    <div className="turn" key={run.id}>
                      <div className="user-message">
                        <span className="mini-avatar">MH</span>
                        <p>{run.user_request}</p>
                      </div>
                      <div className="assistant-message">
                        <span className="assistant-avatar">
                          <Sparkles size={19} />
                        </span>
                        <div className="answer">
                          <div className="answer-heading">
                            <strong>Workplace assistant</strong>
                            <Badge status={run.status} />
                          </div>
                          {run.plan.length > 0 && (
                            <div className="plan">
                              {run.plan.map((step, i) => {
                                const result = run.tool_results.find(
                                  (r) => r.step === i,
                                );
                                return (
                                  <div className="plan-step" key={i}>
                                    <span
                                      className={
                                        "step-icon " +
                                        (result?.ok
                                          ? "done"
                                          : result
                                            ? "failed"
                                            : "")
                                      }
                                    >
                                      {result?.ok ? (
                                        <Check size={12} />
                                      ) : result ? (
                                        <X size={12} />
                                      ) : (
                                        i + 1
                                      )}
                                    </span>
                                    <span>{pretty(step.tool)}</span>
                                    <small>{step.specialist}</small>
                                    {run.status === "awaiting_approval" &&
                                      run.cursor === i && (
                                        <ShieldCheck size={14} />
                                      )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                          <p className="answer-text">{run.final_response}</p>
                          {run.status === "awaiting_approval" &&
                            run.id === active?.id && (
                              <div className="approval-box">
                                <div>
                                  <ShieldCheck size={19} />
                                  <strong>Your approval is needed</strong>
                                </div>
                                <p>
                                  Review the details before this action is sent.
                                </p>
                                <dl>
                                  {Object.entries(
                                    run.plan[run.cursor].args,
                                  ).map(([k, v]) => (
                                    <div key={k}>
                                      <dt>{pretty(k)}</dt>
                                      <dd>{String(v)}</dd>
                                    </div>
                                  ))}
                                </dl>
                                <div className="approval-actions">
                                  <button
                                    className="primary-button"
                                    disabled={busy}
                                    onClick={() => decide(true)}
                                  >
                                    Approve action <Check size={15} />
                                  </button>
                                  <button
                                    className="secondary-button"
                                    disabled={busy}
                                    onClick={() => decide(false)}
                                  >
                                    Reject
                                  </button>
                                </div>
                              </div>
                            )}
                          {run.status === "partial" &&
                            run.id === active?.id && (
                              <button
                                className="secondary-button"
                                disabled={busy}
                                onClick={async () => {
                                  setBusy(true);
                                  try {
                                    setActive(
                                      await api<Run>(
                                        "/runs/" + run.id + "/retry",
                                        { method: "POST" },
                                      ),
                                    );
                                    await refresh();
                                  } catch (e) {
                                    setError((e as Error).message);
                                  } finally {
                                    setBusy(false);
                                  }
                                }}
                              >
                                Retry unfinished steps
                              </button>
                            )}
                          <details className="technical-detail">
                            <summary>View workflow details</summary>
                            <pre>
                              {JSON.stringify(
                                {
                                  id: run.id,
                                  provider: run.provider,
                                  results: run.tool_results,
                                },
                                null,
                                2,
                              )}
                            </pre>
                          </details>
                        </div>
                      </div>
                    </div>
                  ))}
                  {busy && (
                    <div className="thinking" role="status">
                      <Loader2 className="spin" size={18} />
                      <div>
                        <strong>Connecting the right pieces…</strong>
                        <p>
                          Planning your request and checking workplace services.
                        </p>
                      </div>
                    </div>
                  )}
                  <div ref={bottom} />
                </div>
              )}
              <div className="composer-area">
                <form
                  className="composer"
                  onSubmit={(e) => {
                    e.preventDefault();
                    send();
                  }}
                >
                  <label className="sr-only" htmlFor="request">
                    Your workplace request
                  </label>
                  <textarea
                    id="request"
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="What can I take off your plate today?"
                    rows={2}
                    maxLength={4000}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                  />
                  <div className="composer-bottom">
                    <span>
                      <Sparkles size={14} />
                      Workplace assistant{" "}
                      <span className="model-tag">
                        {active?.provider === "remote" ? "LLM" : "Demo"}
                      </span>
                    </span>
                    <button
                      className="send-button"
                      type="submit"
                      disabled={busy || !ready || input.trim().length < 3}
                      aria-label="Send request"
                    >
                      {busy ? (
                        <Loader2 className="spin" size={18} />
                      ) : (
                        <ArrowUp size={20} />
                      )}
                    </button>
                  </div>
                </form>
                <p className="composer-hint">
                  <ShieldCheck size={12} />
                  You’re in control. Sensitive actions always need your
                  approval.<span>↵ to send</span>
                </p>
              </div>
              {!active && !busy && (
                <div className="integrations">
                  <span>CONNECTED TO YOUR DAY</span>
                  <div>
                    <MapPin size={14} />
                    Workplace booking
                    <i />
                    <Ticket size={14} />
                    IT service desk
                    <i />
                    <Users size={14} />
                    Employee directory
                    <i />
                    <BookOpen size={14} />
                    Company knowledge
                  </div>
                </div>
              )}
            </div>
          )}
          {page === "My workflows" && (
            <section className="content-page">
              <PageHeading
                eyebrow="FROM REQUEST TO DONE"
                title="Your work, in motion."
                description="Every step, decision, and outcome. Right where you left it."
              />
              <div className="stats">
                <Stat label="Total workflows" value={runs.length} />
                <Stat
                  label="Completed"
                  value={runs.filter((r) => r.status === "completed").length}
                />
                <Stat label="Awaiting you" value={pending} />
              </div>
              <div className="table-card">
                <div className="table-title">
                  <h3>All workflows</h3>
                  <span>{runs.length} requests</span>
                </div>
                {runs.length === 0 ? (
                  <Empty
                    icon={LayoutGrid}
                    title="Your first workflow starts with a conversation"
                    text="Ask the assistant to book a desk or help you get set up."
                  />
                ) : (
                  runs.map((run) => (
                    <button
                      className="workflow-row"
                      key={run.id}
                      onClick={() => openRun(run)}
                    >
                      <span className="row-icon">
                        <Sparkles size={17} />
                      </span>
                      <div>
                        <strong>{run.user_request}</strong>
                        <small>
                          {new Date(run.created_at).toLocaleString()} ·{" "}
                          {run.plan.length} steps
                        </small>
                      </div>
                      <Badge status={run.status} />
                      <ChevronRight size={17} />
                    </button>
                  ))
                )}
              </div>
            </section>
          )}
          {page === "Spaces" && (
            <section className="content-page">
              <PageHeading
                eyebrow="ROOM TO DO YOUR BEST WORK"
                title="Find your place."
                description="A quiet corner, a team desk, or space for the next big idea."
              />
              <div className="space-search">
                <div>
                  <MapPin size={18} />
                  <strong>{preferences.building} office</strong>
                  <span>Desks & meeting rooms</span>
                </div>
                <button
                  className="primary-button"
                  onClick={() =>
                    send(`Find a desk in ${preferences.building} tomorrow`)
                  }
                >
                  Check availability <ArrowRight size={16} />
                </button>
              </div>
              <div className="space-grid">
                {[
                  {
                    name: "Engineering neighborhood",
                    type: "Team desks",
                    zone: "Engineering",
                    cls: "engineering",
                  },
                  {
                    name: "Quiet corner",
                    type: "Focus desks",
                    zone: "Quiet",
                    cls: "quiet",
                  },
                  {
                    name: "Palm meeting room",
                    type: "Up to 8 people",
                    zone: "room",
                    cls: "meeting",
                  },
                ].map((s) => (
                  <article className="space-card" key={s.name}>
                    <div className={"space-illustration " + s.cls}>
                      <div className="floor-grid">
                        <span />
                        <span />
                        <span />
                        <span />
                        <span />
                        <span />
                      </div>
                      <span className="space-label">DUBAI · FLOOR 3</span>
                    </div>
                    <div className="space-card-body">
                      <span>{s.type}</span>
                      <h3>{s.name}</h3>
                      <button
                        className="text-button"
                        onClick={() =>
                          send(
                            s.zone === "room"
                              ? "Book a meeting room in Dubai tomorrow for 6 from 10:00 to 11:00"
                              : `Book a desk in the ${s.zone} zone in Dubai tomorrow`,
                          )
                        }
                      >
                        Book a space <ArrowRight size={15} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              <h2 className="section-title">
                My reservations <span>{confirmed.length}</span>
              </h2>
              {resources.reservation?.length ? (
                resources.reservation.map((r) => (
                  <div className="resource-row" key={r.id}>
                    <MapPin size={18} />
                    <div>
                      <strong>{r.resource?.name}</strong>
                      <small>
                        {r.start_time?.replace("T", " · ")} →{" "}
                        {r.end_time?.split("T")[1]} · {r.id}
                      </small>
                    </div>
                    <Badge status={r.status} />
                    {r.status === "confirmed" && (
                      <button
                        className="text-button"
                        onClick={() => send(`Cancel reservation ${r.id}`)}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <Empty
                  icon={MapPin}
                  title="A space with your name on it"
                  text="Your desk and room reservations will appear here."
                />
              )}
            </section>
          )}
          {page === "IT support" && (
            <section className="content-page">
              <PageHeading
                eyebrow="LET’S GET YOU UNSTUCK"
                title="A little help goes a long way."
                description="Request equipment, report an issue, or check on a ticket."
              />
              <div className="support-actions">
                {[
                  "Request a monitor",
                  "My VPN is not working",
                  "I need software installed",
                ].map((text) => (
                  <button key={text} onClick={() => send(text)}>
                    <Monitor size={22} />
                    <strong>{text}</strong>
                    <ArrowRight size={17} />
                  </button>
                ))}
              </div>
              <h2 className="section-title">
                My tickets <span>{resources.ticket?.length || 0}</span>
              </h2>
              {resources.ticket?.length ? (
                resources.ticket.map((t) => (
                  <div className="resource-row" key={t.id}>
                    <Ticket size={18} />
                    <div>
                      <strong>{t.description}</strong>
                      <small>
                        {t.id} · {t.category} · {t.priority} priority
                      </small>
                    </div>
                    <Badge status={t.status} />
                    <button
                      className="text-button"
                      onClick={() => send(`Check ticket ${t.id}`)}
                    >
                      Check status
                    </button>
                  </div>
                ))
              ) : (
                <Empty
                  icon={Ticket}
                  title="All clear for now"
                  text="Need a hand? Create a support request above."
                />
              )}
            </section>
          )}
          {page === "Knowledge" && (
            <section className="content-page">
              <PageHeading
                eyebrow="GOOD QUESTIONS. GROUNDED ANSWERS."
                title="Know your workplace."
                description="Find the essentials, with an answer you can trace back to its source."
              />
              <SearchBox
                placeholder="Search policies, onboarding, office hours…"
                onSearch={(q) => send("Search workplace policies: " + q)}
              />
              <div className="knowledge-grid">
                {[
                  {
                    title: "Your first week",
                    desc: "Everything you need for a smooth start.",
                    q: "What are the onboarding requirements?",
                    icon: Sparkles,
                  },
                  {
                    title: "Spaces & booking",
                    desc: "Make the most of your office days.",
                    q: "What is the desk and meeting room booking policy?",
                    icon: MapPin,
                  },
                  {
                    title: "Building access",
                    desc: "Getting where you need to be.",
                    q: "What is the building access policy?",
                    icon: ShieldCheck,
                  },
                  {
                    title: "Hybrid working",
                    desc: "Office hours and flexible arrangements.",
                    q: "What is the hybrid work policy and office hours?",
                    icon: Clock3,
                  },
                ].map(({ title, desc, q, icon: Icon }) => (
                  <button
                    key={title}
                    className="knowledge-card"
                    onClick={() => send(q)}
                  >
                    <Icon size={23} />
                    <h3>{title}</h3>
                    <p>{desc}</p>
                    <span>
                      Read with assistant <ArrowRight size={14} />
                    </span>
                  </button>
                ))}
              </div>
              <p className="source-note">
                <BookOpen size={14} />
                Demo company policies · Reviewed October 2026 · Sources included
                in every answer
              </p>
            </section>
          )}
          {page === "People" && (
            <section className="content-page">
              <PageHeading
                eyebrow="THE PEOPLE BEHIND THE WORK"
                title="Find your next connection."
                description="A teammate, a team lead, or just the right person to ask."
              />
              <SearchBox
                placeholder="Search a name or team…"
                onSearch={(q) => send("Find employee " + q)}
              />
              <div className="people-intro">
                <Users size={35} />
                <h2>Good work starts with people.</h2>
                <p>Search the employee directory by name or team.</p>
                <div>
                  {["Engineering", "People", "IT"].map((team) => (
                    <button
                      className="secondary-button"
                      key={team}
                      onClick={() => send("Find the " + team + " team")}
                    >
                      {team}
                      <ArrowRight size={14} />
                    </button>
                  ))}
                </div>
              </div>
            </section>
          )}
          {page === "Preferences" && (
            <section className="content-page">
              <PageHeading
                eyebrow="MAKE YOURSELF AT HOME"
                title="A workspace that knows you."
                description="Save only what’s useful. Update or forget your preferences at any time."
              />
              <form
                className="settings-card"
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await api("/preferences", {
                      method: "PUT",
                      body: JSON.stringify(preferences),
                    });
                    setSaved(true);
                    setTimeout(() => setSaved(false), 3000);
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                <h3>Your workplace preferences</h3>
                <p>
                  Used when you haven’t specified a location in your request.
                </p>
                <label>
                  Preferred office
                  <select
                    value={preferences.building}
                    onChange={(e) =>
                      setPreferences({
                        ...preferences,
                        building: e.target.value,
                      })
                    }
                  >
                    <option>Dubai</option>
                    <option>London</option>
                  </select>
                </label>
                <label>
                  Preferred desk zone
                  <select
                    value={preferences.zone}
                    onChange={(e) =>
                      setPreferences({ ...preferences, zone: e.target.value })
                    }
                  >
                    <option>Engineering</option>
                    <option>Quiet</option>
                    <option value="">No preference</option>
                  </select>
                </label>
                <div className="settings-footer">
                  <button type="submit" className="primary-button">
                    {saved ? (
                      <>
                        <Check size={15} />
                        Saved
                      </>
                    ) : (
                      "Save preferences"
                    )}
                  </button>
                  <button
                    type="button"
                    className="text-button"
                    onClick={async () => {
                      await api("/preferences", { method: "DELETE" });
                      setPreferences({ building: "Dubai", zone: "" });
                      setSaved(true);
                    }}
                  >
                    Forget my preferences
                  </button>
                </div>
                <small>
                  <ShieldCheck size={13} />
                  Preferences expire after 90 days. Workflow history is retained
                  for 7 days.
                </small>
              </form>
              <div className="settings-card connection-card">
                <h3>Connected capabilities</h3>
                <p>
                  {Object.keys(tools).length} tools discovered across workplace
                  services.
                </p>
                {[
                  "Workplace booking · MCP",
                  "IT service desk · MCP",
                  "Employee directory · REST",
                  "Company policies · Search",
                ].map((name, i) => (
                  <div key={name}>
                    <span>{name}</span>
                    <span
                      className={
                        "badge " +
                        ((i === 0 && !tools.search_rooms) ||
                        (i === 1 && !tools.create_it_ticket)
                          ? "failed"
                          : "completed")
                      }
                    >
                      {(i === 0 && !tools.search_rooms) ||
                      (i === 1 && !tools.create_it_ticket)
                        ? "Unavailable"
                        : "Connected"}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </main>
        <footer className="page-footer">
          <span>Built for the way you work.</span>
          <span>
            <span className="pulse-dot" />
            WorkplaceOS · Local demo
          </span>
        </footer>
      </div>
      {showActivity && (
        <div className="drawer-backdrop" onClick={() => setShowActivity(false)}>
          <aside
            className="activity-drawer"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2>Workspace activity</h2>
              <button
                aria-label="Close activity"
                onClick={() => setShowActivity(false)}
              >
                <X size={20} />
              </button>
            </div>
            <p>Every action leaves a clear trail.</p>
            {audit.length === 0 ? (
              <p>No activity yet.</p>
            ) : (
              audit.slice(0, 40).map((a) => (
                <article key={a.id}>
                  <span className="activity-dot" />
                  <div>
                    <strong>{pretty(a.event)}</strong>
                    {a.tool && <span>{pretty(a.tool)}</span>}
                    <small>{new Date(a.at).toLocaleString()}</small>
                  </div>
                </article>
              ))
            )}
          </aside>
        </div>
      )}
      {login && (
        <div className="login-backdrop">
          <form
            className="login-card"
            onSubmit={(e) => {
              e.preventDefault();
              signIn();
            }}
          >
            <div className="assistant-avatar">
              <Sparkles size={24} />
            </div>
            <span className="eyebrow">WELCOME TO WORKPLACEOS</span>
            <h2>Your workday starts here.</h2>
            <p>Explore a connected workplace with the local demo account.</p>
            <label>
              Demo access code
              <input
                autoComplete="off"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </label>
            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}
            <button className="primary-button" type="submit">
              Enter workspace <ArrowRight size={16} />
            </button>
            <small>Local demo · Fictional company data</small>
          </form>
        </div>
      )}
    </div>
  );
}
function PageHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="page-heading">
      <span className="eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
  );
}
function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value.toString().padStart(2, "0")}</strong>
    </div>
  );
}
function Empty({
  icon: Icon,
  title,
  text,
}: {
  icon: LucideIcon;
  title: string;
  text: string;
}) {
  return (
    <div className="empty">
      <Icon size={28} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function SearchBox({
  placeholder,
  onSearch,
}: {
  placeholder: string;
  onSearch: (q: string) => void;
}) {
  const [q, setQ] = useState("");
  return (
    <form
      className="search-box"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) onSearch(q);
      }}
    >
      <Search size={19} />
      <input
        aria-label={placeholder}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
      />
      <button className="primary-button" disabled={!q.trim()}>
        Search <ArrowRight size={15} />
      </button>
    </form>
  );
}
export default App;

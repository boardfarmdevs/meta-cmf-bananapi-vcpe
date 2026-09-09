import { createContext, useContext, useState, type ReactNode } from 'react';
import {
  Network,
  Router,
  Radio,
  Laptop,
  Terminal,
  Globe,
  ArrowUpRight,
  Layers,
  ChevronRight,
  Cpu,
  FlaskConical,
  MousePointer2,
  Cable,
} from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { entries, source, revision } from './system';
import { Topology, ProtocolPaths, CurrentState, type Inspect } from './views';

const InspectContext = createContext<Inspect>(() => {});
function Block({
  id,
  label,
  sub,
}: {
  id: string;
  label: string;
  sub?: string;
}) {
  const inspect = useContext(InspectContext);
  return (
    <button className="inner-block" onClick={() => inspect(id)}>
      <span>{label}</span>
      {sub && <small>{sub}</small>}
      <ChevronRight size={14} />
    </button>
  );
}
function Card({
  id,
  where,
  title,
  tag,
  caption,
  count,
  icon,
  children,
}: {
  id: string;
  where: string;
  title: string;
  tag: string;
  caption?: string;
  count?: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  const inspect = useContext(InspectContext);
  return (
    <article className={`system-card ${entries[id].color} ${where}`}>
      <button className="card-heading" onClick={() => inspect(id)}>
        {icon}
        <div>
          <span className="overline">{tag}</span>
          <h2>{title}</h2>
        </div>
        {count ? (
          <span className="count-chip">{count}</span>
        ) : (
          <ArrowUpRight size={17} />
        )}
      </button>
      {caption && <div className="role-caption">{caption}</div>}
      <div className="card-body">{children}</div>
    </article>
  );
}

export default function Explorer() {
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState('architecture');
  const [extra, setExtra] = useState<
    { title: string; properties: [string, string][] } | undefined
  >();
  const baseItem = selected ? entries[selected] : null;
  const item =
    baseItem && extra
      ? {
          ...baseItem,
          title: extra.title,
          properties: [...extra.properties, ...baseItem.properties],
        }
      : baseItem;
  const inspect: Inspect = (id, context) => {
    setExtra(context);
    setSelected(id);
  };
  return (
    <InspectContext.Provider value={inspect}>
      <main>
        <header className="masthead">
          <div className="brand">
            <span className="brand-icon">
              <Network size={23} />
            </span>
            <strong>
              EasyMesh <span>LAB</span>
            </strong>
            <span className="divider" />
            <span className="app-name">Architecture explorer</span>
          </div>
          <a
            className="source-link"
            href={source('')}
            target="_blank"
            rel="noreferrer"
          >
            Source documentation <ArrowUpRight size={16} />
          </a>
        </header>
        <section className="page-intro">
          <div>
            <div className="eyebrow">RDK-B · BANANA PI R4 EVALUATION LAB</div>
            <h1>A whole mesh. Under the hood.</h1>
            <p>
              Explore the containers, software stacks, and connections that make
              the lab work.
            </p>
          </div>
          <div className="version">
            <span className="version-dot" /> Documented system
            <span className="branch">
              codex/0908-clean · {revision.slice(0, 7)}
            </span>
          </div>
        </section>
        <Tabs
          value={view}
          onValueChange={(v) => setView(String(v))}
          className="workspace"
        >
          <div className="toolbar">
            <TabsList className="view-tabs" variant="line">
              <TabsTrigger value="architecture">
                <Layers size={16} />
                Architecture
              </TabsTrigger>
              <TabsTrigger value="topology">
                <Network size={16} />
                Network topology
              </TabsTrigger>
              <TabsTrigger value="flows">
                <Cable size={16} />
                Protocol paths
              </TabsTrigger>
              <TabsTrigger value="state">
                <FlaskConical size={16} />
                Current state
              </TabsTrigger>
            </TabsList>
            <span className="offline-label">
              EXPLANATORY MODEL · NO LIVE CONNECTION
            </span>
          </div>
          <TabsContent value="architecture">
            <div className="map-toolbar">
              <div className="legend">
                {[
                  ['blue', 'RDK-B gateway'],
                  ['cyan', 'Extenders'],
                  ['pink', 'Clients'],
                  ['purple', 'Radio simulation'],
                  ['green', 'Lab tooling'],
                  ['amber', 'WAN'],
                ].map(([c, t]) => (
                  <span key={c} className={c}>
                    {t}
                  </span>
                ))}
              </div>
              <span className="map-hint">
                <MousePointer2 size={14} /> Select any block to inspect
              </span>
            </div>
            <div className="map-scroll">
              <div className="system-map">
                <svg
                  className="wiring"
                  viewBox="0 0 1200 915"
                  aria-hidden="true"
                >
                  <defs>
                    {['amber', 'blue', 'cyan', 'purple', 'green'].map((c) => (
                      <marker
                        key={c}
                        id={`arrow-${c}`}
                        viewBox="0 0 10 10"
                        refX="9"
                        refY="5"
                        markerWidth="6"
                        markerHeight="6"
                        orient="auto-start-reverse"
                      >
                        <path d="M0 0 L10 5 L0 10z" className={c} />
                      </marker>
                    ))}
                  </defs>
                  <path
                    className="amber"
                    d="M264 120H326"
                    markerEnd="url(#arrow-amber)"
                  />
                  <path
                    className="blue wireless"
                    d="M746 172H822"
                    markerEnd="url(#arrow-blue)"
                  />
                  <path
                    className="cyan wireless"
                    d="M992 312V362"
                    markerEnd="url(#arrow-cyan)"
                  />
                  <path
                    className="blue wireless"
                    d="M746 421H782V507H822"
                    markerEnd="url(#arrow-blue)"
                  />
                  <path
                    className="purple"
                    d="M536 607V664"
                    markerEnd="url(#arrow-purple)"
                  />
                  <path
                    className="purple"
                    d="M1162 174H1183V800H746"
                    markerEnd="url(#arrow-purple)"
                  />
                  <path className="purple" d="M1162 510H1183" />
                  <path
                    className="green"
                    d="M264 371H295V297H326"
                    markerEnd="url(#arrow-green)"
                  />
                  <path
                    className="green"
                    d="M264 496H295V738H326"
                    markerEnd="url(#arrow-green)"
                  />
                </svg>
                <Card
                  id="wan"
                  where="wan"
                  title="WAN & Internet"
                  tag="BOARDFARM INFRASTRUCTURE"
                  icon={<Globe />}
                >
                  <Block
                    id="dhcp"
                    label="dhcp-cpe1"
                    sub="Kea DHCPv4 / DHCPv6"
                  />
                  <Block
                    id="nat"
                    label="wan-cpe1"
                    sub="Gateway · NAT · Internet"
                  />
                  <div className="interface">br-wan101 → erouter0</div>
                </Card>
                <Card
                  id="tooling"
                  where="tooling"
                  title="Experiment tooling"
                  tag="HOST / APPLIANCE VM"
                  icon={<FlaskConical />}
                >
                  <Block
                    id="optimizer"
                    label="Reference optimizer"
                    sub="Observe → decide → verify"
                  />
                  <Block
                    id="steer"
                    label="Steering adapter"
                    sub="gen/steer.sh · exact BSSID"
                  />
                  <Block
                    id="configurator"
                    label="RF configurator"
                    sub="YAML worlds → timed SNR"
                  />
                  <Block
                    id="console"
                    label="wmediumd Console"
                    sub="Graph · counters · events :8890"
                  />
                  <Block
                    id="room"
                    label="Interactive room"
                    sub="Geometry · playback · RF :8891"
                  />
                  <Block
                    id="tests"
                    label="Validation & lifecycle"
                    sub="gen/tests · LXD orchestration"
                  />
                </Card>
                <Card
                  id="gateway"
                  where="gateway"
                  title="bpibroadband"
                  tag="RDK-B · LXD CONTAINER"
                  caption="Router + EasyMesh controller + colocated Agent-1"
                  count="×1"
                  icon={<Router />}
                >
                  <button className="cli-block" onClick={() => inspect('cli')}>
                    <span>
                      <Terminal size={18} />
                      <strong>EM CLI / WebUI</strong>
                      <small>onewifi_em_cli · :8888</small>
                    </span>
                    <span className="mini-topology" aria-hidden="true">
                      <i />
                      <b />
                      <i />
                      <i />
                      <i />
                    </span>
                    <span className="cli-action">
                      Network topology <ArrowUpRight size={14} />
                    </span>
                  </button>
                  <div className="block-grid">
                    <Block
                      id="controller"
                      label="EasyMesh controller"
                      sub="onewifi_em_ctrl"
                    />
                    <Block
                      id="database"
                      label="MariaDB"
                      sub="OneWifiMesh model"
                    />
                    <Block
                      id="agent"
                      label="Colocated Agent-1"
                      sub="onewifi_em_agent"
                    />
                    <Block
                      id="ieee1905"
                      label="IEEE 1905.1"
                      sub="Controller + agent AL-SAP"
                    />
                  </div>
                  <div className="stack-connector">
                    ↕ RBus / WebConfig · metrics & raw frames
                  </div>
                  <Block
                    id="onewifi"
                    label="OneWifi"
                    sub="Embedded hostap + supplicant"
                  />
                  <Block
                    id="hal"
                    label="RDK Wi-Fi HAL"
                    sub="nl80211 → kernel"
                  />
                  <div className="radio-strip">
                    {['2.4', '5', '6'].map((b) => (
                      <button key={b} onClick={() => inspect('radios')}>
                        {b} GHz
                      </button>
                    ))}
                  </div>
                  <button
                    className="interface"
                    onClick={() => inspect('bridge')}
                  >
                    brlan0 · WDS · routing / firewall <ChevronRight size={13} />
                  </button>
                </Card>
                <Card
                  id="extender"
                  where="extenders"
                  title="EasyMesh extenders"
                  tag="RDK-B · LXD CONTAINERS"
                  caption="bpiap · bpiap-001 · bpiap-002 · bpiap-003"
                  count="×4"
                  icon={<Radio />}
                >
                  <div className="block-grid">
                    <Block
                      id="agent"
                      label="EasyMesh agent"
                      sub="em_agent + ieee1905"
                    />
                    <Block
                      id="onewifi"
                      label="OneWifi + HAL"
                      sub="hostap / supplicant"
                    />
                  </div>
                  <Block
                    id="backhaul"
                    label="5 GHz backhaul STA + AP"
                    sub="brlan0 · 4-address WDS · star / multihop"
                  />
                  <Block
                    id="fronthaul"
                    label="Tri-band fronthaul"
                    sub="private_ssid + iot_ssid · 2.4 / 5 / 6 GHz"
                  />
                </Card>
                <Card
                  id="client"
                  where="clients"
                  title="WLAN clients"
                  tag="ALPINE LINUX · LXD CONTAINERS"
                  caption="10 private stations + 10 IoT stations"
                  count="×20"
                  icon={<Laptop />}
                >
                  <Block
                    id="supplicant"
                    label="wpa_supplicant 2.10"
                    sub="Custom WNM-enabled build · nl80211"
                  />
                  <div className="capability-row">
                    {[
                      ['11k', '802.11k'],
                      ['11r', '802.11r'],
                      ['11v', '802.11v'],
                    ].map(([id, t]) => (
                      <button key={id} onClick={() => inspect(id)}>
                        {t}
                      </button>
                    ))}
                  </div>
                  <Block
                    id="dhcpclient"
                    label="DHCPv4 client"
                    sub="BusyBox udhcpc · lease on wlan0"
                  />
                  <div className="interface dual">
                    <span>
                      wlan0 <b>Wi-Fi + data</b>
                    </span>
                    <span>
                      eth0 <b>Management only</b>
                    </span>
                  </div>
                </Card>
                <Card
                  id="medium"
                  where="medium"
                  title="The simulated RF plane"
                  tag="SHARED LINUX 7.0 KERNEL + HOST DAEMON"
                  icon={<Cpu />}
                >
                  <div className="block-grid">
                    <Block
                      id="hwsim"
                      label="mac80211_hwsim"
                      sub="One wiphy per participant"
                    />
                    <Block
                      id="wmediumd"
                      label="wmediumd.patched"
                      sub="SNR · channels · frame delivery"
                    />
                  </div>
                  <div className="stack-connector">
                    ↔ generic netlink · real 802.11 frames
                  </div>
                  <div className="interface">
                    Every wireless link passes through this plane.
                  </div>
                </Card>
                <button
                  className="wire-label wan-label amber"
                  onClick={() => inspect('wan')}
                >
                  WAN
                </button>
                <button
                  className="wire-label bh-label blue"
                  onClick={() => inspect('backhaul')}
                >
                  Backhaul
                </button>
                <button
                  className="wire-label fh-label cyan"
                  onClick={() => inspect('fronthaul')}
                >
                  Fronthaul
                </button>
                <button
                  className="wire-label radio-label purple"
                  onClick={() => inspect('radios')}
                >
                  hwsim radio
                </button>
                <div className="map-note">
                  <span className="line-key" /> API / local / wired{' '}
                  <span className="line-key dashed" /> Wireless relationship{' '}
                  <span className="note-spacer" /> Container internals are
                  clickable.
                </div>
              </div>
            </div>
          </TabsContent>
          <TabsContent value="topology">
            <Topology inspect={inspect} />
          </TabsContent>
          <TabsContent value="flows">
            <ProtocolPaths inspect={inspect} />
          </TabsContent>
          <TabsContent value="state">
            <CurrentState inspect={inspect} />
          </TabsContent>
        </Tabs>
        <footer>
          <span>
            Real Wi-Fi & EasyMesh protocols. Simulated radios & propagation.
          </span>
          <a href={source('current-state.md')} target="_blank" rel="noreferrer">
            0908 source snapshot <ArrowUpRight size={13} />
          </a>
        </footer>
        <Sheet
          open={!!item}
          onOpenChange={(open) => {
            if (!open) setSelected(null);
          }}
        >
          <SheetContent className={`detail-sheet ${item?.color || 'blue'}`}>
            <SheetHeader>
              <span className="eyebrow">COMPONENT INSPECTOR</span>
              <SheetTitle>{item?.title}</SheetTitle>
              <SheetDescription>{item?.summary}</SheetDescription>
            </SheetHeader>
            {item && (
              <div className="detail-body">
                <div className="detail-tag">{item.kind}</div>
                <h3>Inside this block</h3>
                <p>{item.description}</p>
                <dl>
                  {item.properties.map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
                {item.note && <div className="detail-note">{item.note}</div>}
                {selected === 'cli' && (
                  <button
                    className="action-button"
                    onClick={() => {
                      setSelected(null);
                      setView('topology');
                    }}
                  >
                    Explore network topology <Network size={16} />
                  </button>
                )}
                <h3>Connected components</h3>
                <div className="related">
                  {item.related.map((id) => (
                    <button key={id} onClick={() => inspect(id)}>
                      {entries[id].title}
                      <ChevronRight size={15} />
                    </button>
                  ))}
                </div>
                <h3>Source references</h3>
                {item.sources.map((s) => (
                  <a
                    className="detail-source"
                    href={
                      s.startsWith('gen/')
                        ? `https://github.com/boardfarmdevs/meta-cmf-bananapi-vcpe/blob/${revision}/${s}`
                        : source(s)
                    }
                    key={s}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {s.split('/').pop()}
                    <ArrowUpRight size={15} />
                  </a>
                ))}
              </div>
            )}
          </SheetContent>
        </Sheet>
      </main>
    </InspectContext.Provider>
  );
}

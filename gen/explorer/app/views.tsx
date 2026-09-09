import { useState } from 'react';
import {
  Network,
  Router,
  Radio,
  Laptop,
  ArrowRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Check,
  Info,
  CircleCheck,
  Clock3,
} from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { entries, source } from './system';
export type Inspect = (
  id: string,
  extra?: { title: string; properties: [string, string][] },
) => void;

export function Topology({ inspect }: { inspect: Inspect }) {
  const [shape, setShape] = useState('star');
  const positions = [40, 305, 570, 835];
  const parents =
    shape === 'star'
      ? ['Agent-1', 'Agent-1', 'Agent-1', 'Agent-1']
      : shape === 'chain'
        ? ['Agent-1', 'Extender-1', 'Extender-2', 'Extender-3']
        : ['Agent-1', 'Extender-1', 'Extender-1', 'Extender-3'];
  function clients(group: number) {
    return (
      <div className="client-group">
        {Array.from({ length: 4 }, (_, i) => {
          const cohort = i < 2 ? 'Private' : 'IoT';
          const n = group * 2 + (i % 2) + 1;
          const name = `${i < 2 ? 'STA' : 'IoT'}-${n.toString(16).toUpperCase().padStart(2, '0')}`;
          const ap = group === 0 ? 'Agent-1' : `Extender-${group}`;
          const band = ['2.4', '5', '6'][(group + i) % 3];
          return (
            <button
              key={name}
              className={`top-client ${i < 2 ? 'private' : 'iot'}`}
              onClick={() =>
                inspect('client', {
                  title: name,
                  properties: [
                    ['Example placement', ap],
                    ['SSID', i < 2 ? 'private_ssid' : 'iot_ssid'],
                    ['Example band', `${band} GHz`],
                    ['Data status', 'Illustrative assignment; no live metrics'],
                  ],
                })
              }
            >
              <Laptop size={16} />
              <span>
                {name}
                <small>
                  {band} GHz · {cohort}
                </small>
              </span>
            </button>
          );
        })}
      </div>
    );
  }
  return (
    <section className="topology-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">INSIDE ONEWIFI_EM_CLI · :8888</div>
          <h2>Network Topology</h2>
          <p>An explorable example of the native topology screen.</p>
        </div>
        <button className="quiet-button" onClick={() => inspect('cli')}>
          How this screen gets its data <ArrowUpRight size={15} />
        </button>
      </div>
      <div className="topology-stats">
        {[
          ['5', 'Mesh devices'],
          ['15', 'Logical radios'],
          ['50', 'BSS records'],
          ['20', 'WLAN clients'],
        ].map(([v, l]) => (
          <div key={l}>
            <strong>{v}</strong>
            <span>{l}</span>
          </div>
        ))}
        <div className="model-badge">
          <Info size={17} />
          <span>
            Illustrative topology
            <br />
            <small>Example placements · no live signal values</small>
          </span>
        </div>
      </div>
      <div className="topology-controls">
        <Tabs value={shape} onValueChange={(v) => setShape(String(v))}>
          <TabsList className="segmented">
            <TabsTrigger value="star">Star</TabsTrigger>
            <TabsTrigger value="chain">Chain</TabsTrigger>
            <TabsTrigger value="branch">Branch</TabsTrigger>
          </TabsList>
        </Tabs>
        <span>
          Explore backhaul arrangements; changing this view only changes the
          diagram.
        </span>
      </div>
      <div className="topology-scroll">
        <div className="topology-canvas">
          <svg
            className="topology-wires"
            viewBox="0 0 1100 635"
            aria-hidden="true"
          >
            <path className="local" d="M550 86V124" />
            <path className="fh" d="M660 176H730" />
            {positions.map((x, i) => {
              let d;
              if (parents[i] === 'Agent-1') d = `M550 209V275H${x + 105}V330`;
              else {
                let p = Number(parents[i].slice(-1)) - 1;
                d =
                  shape === 'chain'
                    ? `M${positions[p] + 210} 366H${x}`
                    : `M${positions[p] + 105} 330V${294 - p * 15}H${x + 105}V330`;
              }
              return <path key={i} className="bh" d={d} />;
            })}
            {positions.map((x) => (
              <path key={x} className="fh" d={`M${x + 105} 410V443`} />
            ))}
          </svg>
          <button
            className="top-node controller-node"
            onClick={() => inspect('controller')}
          >
            <Network size={21} />
            <span>
              Controller<small>Control-plane identity · no WLAN BSS</small>
            </span>
          </button>
          <button
            className="top-node agent-node"
            onClick={() => inspect('gateway')}
          >
            <Router size={27} />
            <span>
              Agent-1<small>Colocated in bpibroadband</small>
            </span>
            <b>3 radios</b>
          </button>
          <span className="local-caption">local / colocated</span>
          <div className="gateway-clients">
            <div className="group-caption">Agent-1 fronthaul</div>
            {clients(0)}
          </div>
          {positions.map((x, i) => (
            <div className="extender-column" style={{ left: x }} key={i}>
              <button
                className="top-node extender-node"
                onClick={() =>
                  inspect('extender', {
                    title: `Extender-${i + 1}`,
                    properties: [
                      [
                        'Container',
                        i === 0
                          ? 'bpiap'
                          : `bpiap-${String(i).padStart(3, '0')}`,
                      ],
                      ['Example parent', parents[i]],
                      ['Arrangement', shape],
                      ['Radio count', '3 logical radios / 1 wiphy'],
                    ],
                  })
                }
              >
                <Radio size={24} />
                <span>
                  Extender-{i + 1}
                  <small>3 radios · 5 GHz backhaul</small>
                </span>
              </button>
              <div className="client-branch">
                <div className="group-caption">
                  Fronthaul · 4 example clients
                </div>
                {clients(i + 1)}
              </div>
            </div>
          ))}
          <div className="topology-key">
            <span className="line-key dashed" />5 GHz backhaul{' '}
            <span className="line-key pink-line" />
            Client fronthaul <span className="line-key" />
            Local control
          </div>
        </div>
      </div>
      <div className="topology-explanation">
        <Info size={19} />
        <p>
          <strong>Five devices, not six.</strong> The Controller and Agent-1 are
          separate roles in the same gateway. The four other physical devices
          are extenders. Actual clients, BSSIDs, signal and parentage come from
          the controller model; the assignments above are examples.
        </p>
        <button onClick={() => inspect('database')}>
          Inspect the model <ArrowRight size={15} />
        </button>
      </div>
    </section>
  );
}

type Step = { title: string; body: string; ids: string[]; wire: string };
const journeys: Record<
  string,
  { title: string; intro: string; result: string; steps: Step[] }
> = {
  data: {
    title: 'A client packet reaches the WAN',
    intro:
      'Follow real traffic from an Alpine station through an extender and the RDK gateway.',
    result:
      'Association, a WLAN IPv4 lease, authorized bridge forwarding and end-to-end traffic must all work.',
    steps: [
      {
        title: 'Associate and get an IPv4 lease',
        body: 'The custom wpa_supplicant associates wlan0 with a fronthaul BSSID. BusyBox udhcpc obtains a lease through the Wi-Fi LAN path.',
        ids: ['client', 'supplicant', 'dhcpclient'],
        wire: 'nl80211 · 802.11 association · DHCPv4',
      },
      {
        title: 'Transmit to the fronthaul AP',
        body: 'The client’s hwsim radio transmits real 802.11 frames. wmediumd applies the channel and RF delivery model before the extender receives them.',
        ids: ['client', 'medium', 'fronthaul'],
        wire: 'wlan0 → hwsim → wmediumd → AP',
      },
      {
        title: 'Bridge over the wireless backhaul',
        body: 'The extender bridges client traffic from its fronthaul into brlan0 and its backhaul station. Four-address WDS preserves the downstream client MAC.',
        ids: ['fronthaul', 'bridge', 'backhaul'],
        wire: 'Extender brlan0 → backhaul STA → parent AP',
      },
      {
        title: 'Reach the RDK gateway',
        body: 'An authorized WDS/AP-VLAN port joins the gateway’s brlan0. In a multihop arrangement, traffic first traverses the intermediate parent extender.',
        ids: ['backhaul', 'bridge', 'gateway'],
        wire: 'Controller WDS port → brlan0',
      },
      {
        title: 'Route through the WAN',
        body: 'The gateway routes and filters the packet toward erouter0, br-wan101 and the Boardfarm NAT gateway, then the Internet.',
        ids: ['gateway', 'wan', 'nat'],
        wire: 'erouter0 → br-wan101 → wan-cpe1 → Internet',
      },
    ],
  },
  steering: {
    title: 'An EasyMesh steering request',
    intro:
      'The external decision and the standardized Wi-Fi action have different owners.',
    result:
      'A command or 1905 ACK is not sufficient: BTM, reassociation, database/API placement, traffic and stable services must agree.',
    steps: [
      {
        title: 'Observe the real network',
        body: 'The external optimizer reads topology and fresh current-link and eligible candidate RCPI. Incomplete or stale observations must produce no action.',
        ids: ['cli', 'optimizer'],
        wire: 'EasyMesh HTTP APIs → normalized observation',
      },
      {
        title: 'Choose and resolve a target',
        body: 'An opted-in acting run proposes an exact BSSID. The name-aware steering adapter resolves the station, owning agent, SSID and band.',
        ids: ['optimizer', 'steer'],
        wire: 'Policy → gen/steer.sh → STA + BSSID',
      },
      {
        title: 'Send the EasyMesh command',
        body: 'The controller sends a Client Steering Request to the source agent over IEEE 1905.1. This is a Steering Mandate in the commanded lab path.',
        ids: ['controller', 'ieee1905', 'agent'],
        wire: 'AL-SAP → 1905 CMDU → source agent',
      },
      {
        title: 'Send 802.11v BTM from the source VAP',
        body: 'The agent requests a raw-frame action through RBus. OneWifi sends the BTM Request; the WNM-enabled client responds and reassociates to the requested BSS.',
        ids: ['agent', 'onewifi', '11v', 'supplicant'],
        wire: 'RBus → OneWifi source VAP → BTM → client',
      },
      {
        title: 'Verify the outcome',
        body: 'The station kernel link, controller STAList, WebUI placement and traffic are checked. Cooldown and backoff bound later actions.',
        ids: ['client', 'database', 'tests', 'optimizer'],
        wire: 'iw link + DB + API + traffic + restart counters',
      },
    ],
  },
  onboarding: {
    title: 'An extender joins the mesh',
    intro: 'From a radio namespace to a converged EasyMesh device model.',
    result:
      'The documented 20-client health gate is 5 devices / 15 radios / 50 BSSs / 24 associated STAs, including four backhaul STAs.',
    steps: [
      {
        title: 'Assign a simulated radio',
        body: 'LXD orchestration places exactly one hwsim wiphy into each BPI container. OneWifi creates the gateway’s backhaul and fronthaul VAPs.',
        ids: ['tests', 'hwsim', 'onewifi'],
        wire: 'Host wiphy → container network namespace',
      },
      {
        title: 'Authorize the backhaul',
        body: 'The extender backhaul station associates and completes the four-way handshake. Authorized WDS/AP-VLAN ports then join brlan0 and forward.',
        ids: ['extender', 'backhaul', 'bridge'],
        wire: '802.11 association → security → WDS forwarding',
      },
      {
        title: 'Discover the controller',
        body: 'The agent sends AP-Autoconfiguration Search and the controller responds. This control exchange uses the now-working wireless backhaul.',
        ids: ['agent', 'ieee1905', 'controller'],
        wire: 'IEEE 1905.1 AP autoconfiguration',
      },
      {
        title: 'Exchange WSC M1 / M2',
        body: 'M1 supplies the radio RUID and capabilities. The controller returns M2 with the SSID, security and role configuration.',
        ids: ['agent', 'controller', 'radios'],
        wire: 'WSC M1 capabilities → WSC M2 configuration',
      },
      {
        title: 'Create services and converge reports',
        body: 'The agent converts M2 into WebConfig; OneWifi creates the VAPs. Topology, radio, BSS and client reports populate the controller model.',
        ids: ['agent', 'onewifi', 'database', 'tests'],
        wire: 'WebConfig → VAPs → topology / BSS / STA records',
      },
    ],
  },
  rf: {
    title: 'The RF-to-decision feedback loop',
    intro:
      'A deterministic world changes the medium; real Wi-Fi behavior produces the observations.',
    result:
      'Modeled SNR is stimulus. Reported RCPI, station behavior and traffic are evidence. RF changes must not directly call the steering adapter.',
    steps: [
      {
        title: 'Define a world',
        body: 'A scenario declares radio identities, geometry, movement, walls and presence over time. Associations do not redefine the RF world.',
        ids: ['room', 'configurator'],
        wire: 'World / YAML → validated, compiled plan',
      },
      {
        title: 'Apply RF changes atomically',
        body: 'The configurator applies pair SNR or frequency-qualified overrides through the Unix control socket. Generation checks and readback confirm the applied phase.',
        ids: ['configurator', 'wmediumd'],
        wire: 'SOCK_SEQPACKET → atomic controls + readback',
      },
      {
        title: 'Let Wi-Fi react',
        body: 'wmediumd delivers registered frames according to channel and RF conditions. The AP and station state machines react through the normal Linux Wi-Fi stack.',
        ids: ['wmediumd', 'hwsim', 'onewifi', 'client'],
        wire: 'SNR / PER → frame delivery → actual Wi-Fi behavior',
      },
      {
        title: 'Collect independent observations',
        body: 'The Console observes medium links and outcomes. OneWifi/HAL statistics become EasyMesh reports, controller records and API observations.',
        ids: ['console', 'hal', 'agent', 'database'],
        wire: 'Medium telemetry + AP Metrics Response → model',
      },
      {
        title: 'Decide, verify, and restore',
        body: 'The external optimizer can recommend or perform an opted-in bounded action. Experiments verify outcomes and restore the captured RF baseline exactly.',
        ids: ['optimizer', 'steer', 'tests', 'configurator'],
        wire: 'Observed metrics → decision → action → verification',
      },
    ],
  },
};
export function ProtocolPaths({ inspect }: { inspect: Inspect }) {
  const [journey, setJourney] = useState('data');
  const [step, setStep] = useState(0);
  const j = journeys[journey];
  const s = j.steps[step];
  return (
    <section className="flows-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">FOLLOW THE BOUNDARIES</div>
          <h2>One system. Several paths.</h2>
          <p>
            Step through a packet, a command, onboarding, or an RF experiment.
          </p>
        </div>
      </div>
      <Tabs
        value={journey}
        onValueChange={(v) => {
          setJourney(String(v));
          setStep(0);
        }}
      >
        <TabsList className="journey-tabs">
          <TabsTrigger value="data">Client traffic</TabsTrigger>
          <TabsTrigger value="steering">Commanded steering</TabsTrigger>
          <TabsTrigger value="onboarding">Mesh onboarding</TabsTrigger>
          <TabsTrigger value="rf">RF feedback loop</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="journey-layout">
        <div className="step-list" aria-label="Steps">
          {j.steps.map((v, i) => (
            <button
              key={v.title}
              className={i === step ? 'current' : ''}
              aria-current={i === step ? 'step' : undefined}
              onClick={() => setStep(i)}
            >
              <span>
                {i < step ? (
                  <Check size={16} />
                ) : (
                  String(i + 1).padStart(2, '0')
                )}
              </span>
              {v.title}
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
        <article className="step-detail" aria-live="polite">
          <div className="eyebrow">
            {j.title} · {step + 1} / {j.steps.length}
          </div>
          <h3>{s.title}</h3>
          <p>{s.body}</p>
          <div className="path-blocks">
            {s.ids.map((id, i) => (
              <div className="path-block-wrap" key={id}>
                {i > 0 && <ArrowRight className="path-arrow" size={22} />}
                <button
                  className={`path-block ${entries[id].color}`}
                  onClick={() => inspect(id)}
                >
                  <span className="dot" />
                  {entries[id].title}
                  <ArrowUpRight size={14} />
                </button>
              </div>
            ))}
          </div>
          <div className="protocol-strip">{s.wire}</div>
          <div className="step-actions">
            <button
              className="quiet-button"
              disabled={step === 0}
              onClick={() => setStep(step - 1)}
            >
              <ChevronLeft size={16} />
              Previous
            </button>
            <button
              className="action-button"
              onClick={() =>
                setStep(step === j.steps.length - 1 ? 0 : step + 1)
              }
            >
              {step === j.steps.length - 1 ? 'Start again' : 'Next boundary'}
              <ChevronRight size={16} />
            </button>
          </div>
        </article>
      </div>
      <div className="acceptance-note">
        <CircleCheck size={22} />
        <div>
          <strong>What proves this path works</strong>
          <p>{j.result}</p>
        </div>
      </div>
    </section>
  );
}

export function CurrentState({ inspect }: { inspect: Inspect }) {
  return (
    <section className="state-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">CODEX/0908-CLEAN · PINNED DOCUMENTATION</div>
          <h2>The system this page describes</h2>
          <p>
            Current architecture and qualification boundaries, separated from
            example data.
          </p>
        </div>
        <a
          className="quiet-button"
          href={source('current-state.md')}
          target="_blank"
          rel="noreferrer"
        >
          Read the full current state <ArrowUpRight size={16} />
        </a>
      </div>
      <div className="state-grid">
        <article className="state-card">
          <div className="state-icon green">
            <CircleCheck />
          </div>
          <h3>Accepted foundation</h3>
          <ul>
            <li>One gateway, four extenders, twenty WLAN clients.</li>
            <li>
              Five mesh devices, fifteen logical radios and fifty BSS records.
            </li>
            <li>
              Real Wi-Fi, IEEE 1905.1, WSC, bridging and commanded steering.
            </li>
            <li>Patched userspace wmediumd as the accepted default medium.</li>
            <li>
              0908 fresh cold reconstruction with zero native service restarts.
            </li>
          </ul>
          <button onClick={() => inspect('state')}>
            Inspect qualification <ArrowRight size={16} />
          </button>
        </article>
        <article className="state-card">
          <div className="state-icon amber">
            <Clock3 />
          </div>
          <h3>Boundaries to preserve</h3>
          <ul>
            <li>
              The fresh RDK import needed one extender metrics-policy replay.
            </li>
            <li>
              Arbitrary independent node stop/start recovery is not yet
              accepted.
            </li>
            <li>A completed 12-hour churn soak is not claimed.</li>
            <li>
              The external research optimizer is not an autonomous production
              policy.
            </li>
            <li>
              The optional kernel medium is a reduced-physics comparison
              backend.
            </li>
          </ul>
          <button onClick={() => inspect('tests')}>
            Inspect validation gates <ArrowRight size={16} />
          </button>
        </article>
        <article className="state-card">
          <div className="state-icon pink">
            <Laptop />
          </div>
          <h3>Client capability evidence</h3>
          <div className="evidence-list">
            {[
              ['11v', '802.11v', 'Commanded BTM steering documented'],
              [
                '11r',
                '802.11r',
                'Compiled support; runtime FT not established',
              ],
              ['11k', '802.11k', 'Separate runtime qualification needed'],
              ['dhcpclient', 'DHCPv4', 'udhcpc lease on wlan0'],
            ].map(([id, title, t]) => (
              <button key={id} onClick={() => inspect(id)}>
                <strong>{title}</strong>
                <span>{t}</span>
                <ChevronRight size={15} />
              </button>
            ))}
          </div>
        </article>
        <article className="state-card">
          <div className="state-icon blue">
            <Info />
          </div>
          <h3>How to read this explorer</h3>
          <p>
            The architecture comes from the linked repository at a pinned
            revision. Topology placements and band assignments are explanatory
            examples. No live lab is connected.
          </p>
          <p>
            RDK runs on rev140 in the 0908 deployment split. The separate
            prplMesh repository and live room run on rev150.
          </p>
          <p>
            Component inspectors link directly to the source used for each
            boundary.
          </p>
          <button onClick={() => inspect('cli')}>
            Inspect the observation surface <ArrowRight size={16} />
          </button>
        </article>
      </div>
    </section>
  );
}

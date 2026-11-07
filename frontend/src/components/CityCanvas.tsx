import { OrbitControls, OrthographicCamera } from "@react-three/drei";
import { Canvas, ThreeEvent, useFrame } from "@react-three/fiber";
import { ReactNode, useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Building, City, Item } from "../types";

export type Tool = "view" | "build" | "demolish" | "expand";
export type LightingMode = "day" | "dusk" | "night";
const LIGHTING = {
  day: { background: "#d5e5ed", fog: "#d5e5ed", sky: "#f4fbff", ground: "#77836c", hemi: 0.9, ambient: 0.5, key: "#fff0d4", keyPower: 2, fill: "#c5e9ff", fillPower: 0.65 },
  dusk: { background: "#bb8d88", fog: "#bb8d88", sky: "#ffd3a3", ground: "#4b6857", hemi: 0.72, ambient: 0.42, key: "#ffb978", keyPower: 1.35, fill: "#978ce0", fillPower: 0.48 },
  night: { background: "#14213c", fog: "#192944", sky: "#526a9b", ground: "#263a32", hemi: 0.58, ambient: 0.36, key: "#a9c5ff", keyPower: 1.05, fill: "#687ac5", fillPower: 0.36 },
} satisfies Record<LightingMode, { background: string; fog: string; sky: string; ground: string; hemi: number; ambient: number; key: string; keyPower: number; fill: string; fillPower: number }>;
const U = 0.5; // one height unit, identical to the banner renderer
const GROUND = ["#76b062", "#3e84c4", "#e6d096", "#464a56", "#569654", "#8c8070"];

export const footprint = (b: Building, x: number, z: number, rot: number) => {
  const [w, d] = rot % 2 ? [b.d, b.w] : [b.w, b.d];
  const tiles: [number, number][] = [];
  for (let i = 0; i < w; i++) for (let j = 0; j < d; j++) tiles.push([x + i, z + j]);
  return { tiles, w, d };
};
const jitter = (x: number, z: number) => { const s = Math.sin(x * 12.9898 + z * 78.233) * 43758.5453; return 0.94 + 0.1 * (s - Math.floor(s)); };

function Instances({ count, fill, children }: { count: number; fill: (i: number, o: THREE.Object3D, c: THREE.Color) => void; children: ReactNode }) {
  const ref = useRef<THREE.InstancedMesh>(null!);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const o = new THREE.Object3D(), c = new THREE.Color();
    for (let i = 0; i < count; i++) {
      o.position.set(0, 0, 0); o.rotation.set(0, 0, 0); o.scale.set(1, 1, 1);
      fill(i, o, c); o.updateMatrix();
      ref.current.setMatrixAt(i, o.matrix); ref.current.setColorAt(i, c);
    }
    ref.current.instanceMatrix.needsUpdate = true;
    if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true;
  }, [count, fill]);
  if (!count) return null;
  return <instancedMesh key={count} ref={ref} args={[undefined, undefined, count]} castShadow receiveShadow>{children}</instancedMesh>;
}

function Terrain({ city }: { city: City }) {
  const tiles = useMemo(() => {
    const out: { x: number; z: number; h: number; t: number; open: boolean; sidewalk?: boolean }[] = [];
    for (const ch of city.chunks) for (let i = 0; i < ch.t.length; i++)
      out.push({ x: ch.cx * 16 + (i % 16), z: ch.cz * 16 + Math.floor(i / 16), h: ch.h[i], t: ch.t[i], open: ch.unlocked });
    const roads = new Set(out.filter((t) => t.t === 3).map((t) => `${t.x},${t.z}`));
    for (const t of out) t.sidewalk = t.t !== 3 && [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dz]) => roads.has(`${t.x + dx},${t.z + dz}`));
    return out;
  }, [city.chunks]);
  const fill = useCallback((i: number, o: THREE.Object3D, c: THREE.Color) => {
    const t = tiles[i]; const e = t.t === 1 ? 0.2 : U * t.h;
    o.position.set(t.x + 0.5, e / 2, t.z + 0.5); o.scale.set(0.99, e, 0.99);
    c.set(t.sidewalk ? "#b7b4ad" : GROUND[t.t]).multiplyScalar(jitter(t.x, t.z) * (t.open ? 1 : 0.86));
  }, [tiles]);
  const edgeX = (Math.max(...city.unlocked.map(([cx]) => cx)) + 1) * 16 - 1;
  const edgeZ = (Math.max(...city.unlocked.map(([, cz]) => cz)) + 1) * 16 - 1;
  const roads = useMemo(() => tiles.filter((t) => t.t === 3 &&
    ((t.x % 8 === 0 || t.x === edgeX) !== (t.z % 8 === 0 || t.z === edgeZ))), [tiles, edgeX, edgeZ]);
  const mark = useCallback((i: number, o: THREE.Object3D, c: THREE.Color) => {
    const t = roads[i], vertical = t.x % 8 === 0 || t.x === edgeX;
    o.position.set(t.x + 0.5, 0.516, t.z + 0.5);
    o.scale.set(vertical ? 0.055 : 0.42, 0.018, vertical ? 0.42 : 0.055);
    c.set("#f4cc72");
  }, [roads, edgeX]);
  return <>
    <Instances count={tiles.length} fill={fill}><boxGeometry args={[1, 1, 1]} /><meshStandardMaterial roughness={0.92} /></Instances>
    <Instances count={roads.length} fill={mark}><boxGeometry args={[1, 1, 1]} /><meshBasicMaterial /></Instances>
  </>;
}

const SPECIAL = new Set(["tree", "streetlight", "road", "park"]);

function BuildingWindows({ b, preview = false, night = false }: { b: Building; preview?: boolean; night?: boolean }) {
  const windows = useMemo(() => {
    const out: { x: number; y: number; z: number; side: boolean }[] = [];
    const w = b.w * 0.92, d = b.d * 0.92, h = b.h * U;
    const columns = Math.max(1, Math.floor(w / 0.42)), rows = Math.max(1, Math.floor(h / 0.48));
    for (let row = 0; row < rows; row++) {
      const y = U + 0.3 + row * 0.48;
      if (y > U + h - 0.16) continue;
      for (let col = 0; col < columns; col++) {
        const x = -w / 2 + ((col + 1) * w) / (columns + 1);
        out.push({ x, y, z: d / 2 + 0.025, side: false });
      }
      const sideColumns = Math.max(1, Math.floor(d / 0.5));
      for (let col = 0; col < sideColumns; col++) {
        const z = -d / 2 + ((col + 1) * d) / (sideColumns + 1);
        out.push({ x: w / 2 + 0.025, y, z, side: true });
      }
    }
    return out;
  }, [b.w, b.d, b.h]);
  const frame = useCallback((i: number, o: THREE.Object3D, c: THREE.Color) => {
    const win = windows[i];
    o.position.set(win.x, win.y, win.z);
    o.rotation.y = win.side ? Math.PI / 2 : 0;
    o.scale.set(0.29, 0.31, 0.05);
    c.set("#283845");
  }, [windows, preview]);
  const glass = useCallback((i: number, o: THREE.Object3D, c: THREE.Color) => {
    const win = windows[i];
    o.position.set(win.x + (win.side ? 0.032 : 0), win.y, win.z + (win.side ? 0 : 0.032));
    o.rotation.y = win.side ? Math.PI / 2 : 0;
    o.scale.set(0.19, 0.21, 0.025);
    c.set(night ? "#ffd875" : preview ? "#d7f3f4" : "#83cbdc");
  }, [windows, preview, night]);
  return <>
    <Instances count={windows.length} fill={frame}><boxGeometry args={[1, 1, 1]} /><meshBasicMaterial transparent={preview} opacity={preview ? 0.72 : 1} /></Instances>
    <Instances count={windows.length} fill={glass}><boxGeometry args={[1, 1, 1]} /><meshPhysicalMaterial color={night ? "#ffe2a0" : "#b9edf5"} emissive={night ? "#d99b38" : "#000000"} emissiveIntensity={night ? 0.65 : 0} metalness={0.18} roughness={0.16} clearcoat={0.9} clearcoatRoughness={0.12} transparent={preview} opacity={preview ? 0.8 : 0.94} /></Instances>
  </>;
}

const SIGN_TEXTURES = new Map<string, THREE.CanvasTexture>();
function signTexture(label: string, color: string) {
  const key = `${label}:${color}`;
  const old = SIGN_TEXTURES.get(key);
  if (old) return old;
  const canvas = document.createElement("canvas");
  canvas.width = 256; canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#253440"; ctx.fillRect(0, 0, 256, 64);
  ctx.fillStyle = color; ctx.fillRect(4, 4, 248, 56);
  ctx.strokeStyle = "#f1e2bb"; ctx.lineWidth = 4; ctx.strokeRect(3, 3, 250, 58);
  ctx.fillStyle = "#fff4d6"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.font = `700 ${Math.max(12, Math.min(25, 210 / Math.max(8, label.length * 0.66)))}px sans-serif`;
  ctx.fillText(label.toUpperCase(), 128, 32, 220);
  const texture = new THREE.CanvasTexture(canvas);
  texture.magFilter = THREE.LinearFilter; texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.anisotropy = 4;
  texture.colorSpace = THREE.SRGBColorSpace;
  SIGN_TEXTURES.set(key, texture);
  return texture;
}

function BuildingSign({ b, preview = false }: { b: Building; preview?: boolean }) {
  const texture = useMemo(() => signTexture(b.name, b.color), [b.name, b.color]);
  return <mesh position={[0, U + 0.68, b.d * 0.47 + 0.045]}>
    <planeGeometry args={[Math.min(b.w * 0.86, 2.4), 0.38]} />
    <meshBasicMaterial map={texture} transparent={preview} opacity={preview ? 0.72 : 1} toneMapped={false} />
  </mesh>;
}

function BuildingModel({ item, b, highlight = false, preview = false, night = false }: {
  item: Item; b: Building; highlight?: boolean; preview?: boolean; night?: boolean;
}) {
  const f = footprint(b, item.x, item.z, item.rot), h = b.h * U;
  const w = b.w, d = b.d;
  const id = item.type;
  const residential = id === "home" || id === "apartment" || id === "satellite_settlement";
  const apartment = id === "apartment";
  const industrial = ["workshop", "tech_generic", "industrial_complex", "factory", "power_plant", "distribution_warehouse", "container_hub", "airport_terminal", "logistics_hub", "logistics_depot", "repair_depot"].includes(id);
  const civic = b.category === "civic" || b.category === "quality" || id === "library" || id === "services_centre";
  const landmark = b.category === "landmark" || id === "oss_landmark" || id === "trust_monument";
  const bridge = id === "bridge_landmark";
  const utility = id === "utility_station" || id === "fast_utility";
  const laboratory = id === "research_lab" || id === "ai_lab" || id === "vector_lab";
  const campus = ["enterprise_campus", "backend_campus", "mobile_campus", "international_district", "cloud_district", "development_complex", "business_district", "neighbourhood_hub", "creative_commercial"].includes(id);
  const plaza = ["mixed_plaza", "grand_opening_plaza", "visitor_plaza"].includes(id);
  const tower = !residential && !industrial && !civic && !landmark && h > 1.35;
  const color = highlight ? "#e5484d" : b.color;
  const roofColor = highlight ? "#b83b43" : new THREE.Color(b.color).multiplyScalar(0.68).getStyle();
  const windows = !industrial && !bridge && !plaza && !campus && id !== "utility_station" && id !== "fast_utility";
  const floors = Math.max(1, Math.floor(h / 0.48));
  return <group position={[item.x + f.w / 2, 0, item.z + f.d / 2]} rotation-y={item.rot * Math.PI / 2}>
    <mesh position={[0, U + 0.07, 0]} receiveShadow>
      <boxGeometry args={[w * 1.04, 0.14, d * 1.04]} />
      <meshStandardMaterial color={highlight ? color : "#b7aa91"} roughness={0.84} transparent={preview} opacity={preview ? 0.45 : 1} />
    </mesh>
    {bridge ? <>
      <mesh position={[0, U + h * 0.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.98, 0.2, d * 0.76]} /><meshStandardMaterial color="#9c8063" roughness={0.78} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>
      {[-w * 0.32, 0, w * 0.32].map((x, i) => <mesh key={`pier-${i}`} position={[x, U + h * 0.22, 0]} castShadow>
        <cylinderGeometry args={[0.12, 0.18, h * 0.44, 8]} /><meshStandardMaterial color="#786c61" roughness={0.88} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
      {[-1, 1].map((side) => <mesh key={`rail-${side}`} position={[0, U + h * 0.58, side * d * 0.34]}>
        <boxGeometry args={[w * 0.96, 0.08, 0.06]} /><meshStandardMaterial color="#5c6465" metalness={0.5} roughness={0.48} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
    </> : utility ? <>
      <mesh position={[-w * 0.2, U + 0.38, 0]} castShadow>
        <boxGeometry args={[0.52, 0.55, 0.52]} /><meshStandardMaterial color="#d4b958" roughness={0.72} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>
      <mesh position={[w * 0.22, U + 0.28, 0]} castShadow>
        <boxGeometry args={[0.38, 0.35, 0.4]} /><meshStandardMaterial color="#657378" metalness={0.34} roughness={0.52} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>
      {[-0.2, 0, 0.2].map((x, i) => <mesh key={`insulator-${i}`} position={[x, U + 0.72, -d * 0.12]}>
        <cylinderGeometry args={[0.045, 0.06, 0.22, 6]} /><meshStandardMaterial color="#ece5d0" roughness={0.4} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
    </> : industrial ? <>
      <mesh position={[0, U + h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.94, h * 0.88, d * 0.94]} />
        <meshPhysicalMaterial color={color} roughness={0.38} metalness={0.12} clearcoat={0.58} clearcoatRoughness={0.25} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>
      <mesh position={[0, U + h * 0.94, 0]} castShadow>
        <boxGeometry args={[w * 0.99, 0.16, d * 0.99]} />
        <meshStandardMaterial color={roofColor} roughness={0.72} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>
      {[...Array(Math.max(1, Math.floor(w / 2)))].map((_, i) => (
        <group key={`vent-${i}`} position={[-w / 2 + 0.5 + i * 1.5, U + h, d * 0.22]}>
          <mesh castShadow><cylinderGeometry args={[0.12, 0.16, 0.34, 8]} /><meshStandardMaterial color="#858b8d" metalness={0.55} roughness={0.45} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
          <mesh position={[0, 0.2, 0]}><cylinderGeometry args={[0.17, 0.17, 0.06, 8]} /><meshStandardMaterial color="#59646a" metalness={0.6} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
        </group>))}
      {[...Array(Math.max(1, Math.floor(w / 1.2)))].map((_, i, arr) => <mesh key={`loading-${i}`} position={[-w * 0.36 + i * (w * 0.72 / Math.max(1, arr.length - 1)), U + 0.33, d * 0.478]}>
        <boxGeometry args={[0.42, 0.48, 0.06]} /><meshStandardMaterial color="#525e64" metalness={0.22} roughness={0.62} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
      {id === "power_plant" && [-0.28, 0.28].map((x, i) => <mesh key={`cooling-${i}`} position={[x * w, U + h * 0.85, -d * 0.22]} castShadow>
        <cylinderGeometry args={[0.34, 0.24, h * 0.46, 8, 1, true]} /><meshStandardMaterial color="#e7e0cd" side={THREE.DoubleSide} roughness={0.78} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
      {id === "container_hub" && [-0.27, 0, 0.27].map((x, i) => <mesh key={`container-${i}`} position={[x * w, U + h * 0.82, -d * 0.23 + (i % 2) * 0.44]} castShadow>
        <boxGeometry args={[w * 0.24, h * 0.34, d * 0.42]} /><meshStandardMaterial color={i % 2 ? "#df9c50" : "#4f929b"} roughness={0.74} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
    </> : <>
      {tower && <mesh position={[0, U + 0.22, 0]} castShadow>
        <boxGeometry args={[w * 1.08, 0.28, d * 1.08]} />
        <meshStandardMaterial color={roofColor} roughness={0.64} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>}
      {campus ? [-1, 0, 1].map((col, i) => {
        const towerHeight = h * [0.68, 1, 0.78][i];
        return <group key={`campus-${i}`}>
          <mesh position={[col * w * 0.28, U + towerHeight / 2, 0]} castShadow receiveShadow>
            <boxGeometry args={[w * 0.27, towerHeight, d * 0.72]} />
            <meshStandardMaterial color={new THREE.Color(color).multiplyScalar(0.78 + i * 0.12)} roughness={0.4} metalness={0.24} transparent={preview} opacity={preview ? 0.5 : 1} />
          </mesh>
          {[...Array(Math.max(1, Math.floor(towerHeight / 0.48)))].map((_, row) => [-1, 1].map((side) => <mesh key={`campus-window-${row}-${side}`} position={[col * w * 0.28 + side * w * 0.055, U + 0.3 + row * 0.48, d * 0.365]}>
            <boxGeometry args={[0.16, 0.22, 0.045]} /><meshStandardMaterial color="#85cadb" emissive="#24444b" emissiveIntensity={0.18} roughness={0.28} transparent={preview} opacity={preview ? 0.58 : 1} />
          </mesh>))}
        </group>;
      }) : plaza ? [-1, 1].flatMap((x) => [-1, 1].map((z, i) => <mesh key={`pavilion-${x}-${z}`} position={[x * w * 0.26, U + h * 0.25, z * d * 0.26]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.36, h * 0.5, d * 0.36]} />
        <meshStandardMaterial color={i % 2 ? color : roofColor} roughness={0.7} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)) : <mesh position={[0, U + h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w * (tower ? 0.82 : 0.92), h * (residential && !apartment ? 0.72 : 0.9), d * (tower ? 0.82 : 0.92)]} />
        <meshPhysicalMaterial color={color} roughness={tower ? 0.24 : 0.42} metalness={tower ? 0.28 : 0.08} clearcoat={tower ? 0.82 : 0.5} clearcoatRoughness={0.2} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>}
      {residential && !apartment && <mesh position={[0, U + h * 0.88, 0]} castShadow rotation-y={Math.PI / 4}>
        <coneGeometry args={[Math.max(w, d) * 0.68, Math.min(0.75, h * 0.42), 4]} />
        <meshStandardMaterial color={roofColor} roughness={0.83} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>}
      {apartment && [...Array(floors)].map((_, i) => <mesh key={`balcony-${i}`} position={[0, U + 0.34 + i * 0.48, d * 0.49]} castShadow>
        <boxGeometry args={[w * 0.98, 0.07, 0.16]} /><meshStandardMaterial color="#d8d1c3" roughness={0.65} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
      {civic && [...Array(Math.max(2, Math.floor(w / 0.55)))].map((_, i, arr) => {
        const x = -w * 0.35 + (i * w * 0.7) / (arr.length - 1);
        return <mesh key={`column-${i}`} position={[x, U + h * 0.43, d * 0.48]} castShadow>
          <cylinderGeometry args={[0.07, 0.1, Math.min(h * 0.72, 1.5), 8]} />
          <meshStandardMaterial color="#e8ddc7" roughness={0.7} transparent={preview} opacity={preview ? 0.5 : 1} />
        </mesh>;
      })}
      {(tower || civic || landmark) && <mesh position={[0, U + h + 0.08, 0]} castShadow>
        {landmark ? <coneGeometry args={[Math.max(w, d) * 0.3, Math.min(1.2, h * 0.55), 8]} /> : <boxGeometry args={[w * 1.02, 0.14, d * 1.02]} />}
        <meshStandardMaterial color={roofColor} roughness={0.58} metalness={landmark ? 0.25 : 0.05} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>}
      {laboratory && <mesh position={[0, U + h + 0.24, 0]} castShadow>
        <sphereGeometry args={[Math.min(w, d) * 0.33, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#9fd6df" metalness={0.25} roughness={0.3} transparent opacity={preview ? 0.5 : 0.82} />
      </mesh>}
      {["db_tower", "data_warehouse", "lakehouse"].includes(id) && [-0.3, 0.3].map((x, i) => <group key={`silo-${i}`} position={[x * w, U + h + 0.28, 0]}>
        <mesh castShadow><cylinderGeometry args={[0.2, 0.23, 0.56, 8]} /><meshStandardMaterial color="#9fb7b2" metalness={0.3} roughness={0.44} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
        <mesh position={[0, 0.31, 0]}><coneGeometry args={[0.23, 0.18, 8]} /><meshStandardMaterial color="#d7c995" roughness={0.62} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
      </group>)}
      {id === "design_studio" && [...Array(3)].map((_, i) => <mesh key={`sawtooth-${i}`} position={[-w * 0.28 + i * w * 0.28, U + h * 0.94, -d * 0.12]} rotation-z={-0.3} castShadow>
        <boxGeometry args={[w * 0.32, 0.26, d * 0.82]} /><meshStandardMaterial color={i % 2 ? "#9ed4d7" : roofColor} metalness={0.12} roughness={0.42} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
      {id === "stream_hub" && <group position={[0, U + h + 0.26, 0]}>
        <mesh position={[0, 0.24, 0]}><cylinderGeometry args={[0.06, 0.09, 0.48, 8]} /><meshStandardMaterial color="#66747a" metalness={0.5} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
        <mesh position={[0, 0.5, 0]} rotation-x={-0.45}><sphereGeometry args={[0.52, 8, 6, 0, Math.PI * 2, 0, Math.PI / 2]} /><meshStandardMaterial color="#d9e6e4" side={THREE.DoubleSide} roughness={0.42} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
        <mesh position={[0, 0.82, 0]}><sphereGeometry args={[0.075, 8, 6]} /><meshBasicMaterial color="#e9b954" /></mesh>
      </group>}
      {id === "stats_centre" && [-1, 0, 1].map((x, i) => <mesh key={`stat-bar-${i}`} position={[x * 0.38, U + h + 0.12 + i * 0.08, 0]} castShadow>
        <boxGeometry args={[0.24, 0.24 + i * 0.16, 0.24]} /><meshStandardMaterial color={["#5ca9b8", "#e5b64e", "#e47c60"][i]} roughness={0.5} transparent={preview} opacity={preview ? 0.5 : 1} />
      </mesh>)}
      {id === "town_hall" && <group position={[0, U + h * 0.72, d * 0.49]}>
        <mesh><cylinderGeometry args={[0.24, 0.24, 0.08, 12]} /><meshStandardMaterial color="#eee2c5" roughness={0.55} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
        <mesh position={[0, 0, 0.055]}><circleGeometry args={[0.17, 12]} /><meshBasicMaterial color="#415568" /></mesh>
        <mesh position={[0, 0.045, 0.07]}><boxGeometry args={[0.018, 0.1, 0.025]} /><meshBasicMaterial color="#f1d78b" /></mesh>
        <mesh position={[0.045, 0, 0.07]}><boxGeometry args={[0.09, 0.018, 0.025]} /><meshBasicMaterial color="#f1d78b" /></mesh>
      </group>}
      {["broadcast_tower", "automation_tower", "control_tower"].includes(id) && <group position={[0, U + h + 0.18, 0]}>
        <mesh castShadow><cylinderGeometry args={[0.055, 0.09, 0.7, 8]} /><meshStandardMaterial color="#66747a" metalness={0.65} roughness={0.36} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
        <mesh position={[0, 0.43, 0]}><sphereGeometry args={[0.13, 10, 8]} /><meshStandardMaterial color="#e6b94e" emissive="#624c1d" transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
      </group>}
    </>}
    {id === "airport_terminal" && <group position={[-w * 0.28, U + h + 0.24, 0]}>
      <mesh><cylinderGeometry args={[0.13, 0.22, 0.48, 10]} /><meshStandardMaterial color="#8e9ea1" metalness={0.42} roughness={0.35} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
      <mesh position={[0, 0.26, 0]}><cylinderGeometry args={[0.2, 0.2, 0.08, 10]} /><meshStandardMaterial color="#52616a" metalness={0.5} transparent={preview} opacity={preview ? 0.5 : 1} /></mesh>
    </group>}
    {windows && <BuildingWindows b={b} preview={preview} night={night} />}
    {!industrial && !bridge && !utility && <mesh position={[0, U + 0.25, d * 0.47]} castShadow>
      <boxGeometry args={[0.28, 0.42, 0.07]} />
      <meshStandardMaterial color="#49395d" roughness={0.75} transparent={preview} opacity={preview ? 0.6 : 1} />
    </mesh>}
    {!bridge && <BuildingSign b={b} preview={preview} />}
    {landmark && <mesh position={[0, U + h + 0.42, 0]} castShadow>
      <cylinderGeometry args={[0.07, 0.13, 0.75, 8]} />
      <meshStandardMaterial color="#d6b85f" metalness={0.58} roughness={0.35} transparent={preview} opacity={preview ? 0.5 : 1} />
    </mesh>}
  </group>;
}

function Buildings({ items, cat, highlight, night }: { items: Item[]; cat: Record<string, Building>; highlight: number | null; night: boolean }) {
  return <>{items.filter((it) => cat[it.type] && !SPECIAL.has(it.type)).map((it) => (
    <BuildingModel key={it.id} item={it} b={cat[it.type]} highlight={it.id === highlight} night={night} />
  ))}</>;
}

function TownControls({ centre, autoRotateView, onViewAngle }: { centre: [number, number]; autoRotateView: boolean; onViewAngle: (angle: number) => void }) {
  const controls = useRef<any>(null);
  const lastAngle = useRef<number | null>(null);
  useFrame(() => {
    if (!controls.current) return;
    const degrees = THREE.MathUtils.radToDeg(controls.current.getAzimuthalAngle());
    const angle = (Math.round(degrees) + 360) % 360;
    if (angle !== lastAngle.current) {
      lastAngle.current = angle;
      onViewAngle(angle);
    }
  });
  return <OrbitControls ref={controls} target={[centre[0], 0, centre[1]]} enableRotate enablePan enableZoom enableDamping dampingFactor={0.08}
    autoRotate={autoRotateView} autoRotateSpeed={0.55} minPolarAngle={0.2} maxPolarAngle={Math.PI / 2.05}
    minDistance={18} maxDistance={160} />;
}

function Decor({ items, cat, highlight }: { items: Item[]; cat: Record<string, Building>; highlight: number | null }) {
  const of = (t: string) => items.filter(i => i.type === t);
  const trees = useMemo(() => of("tree"), [items]);
  const lights = useMemo(() => of("streetlight"), [items]);
  const roads = useMemo(() => of("road"), [items]);
  const parks = useMemo(() => of("park"), [items]);
  const hl = (c: THREE.Color, id: number, base: string) => c.set(id === highlight ? "#e5484d" : base);
  return (<>
    <Instances count={trees.length} fill={useCallback((i, o, c) => {
      const t = trees[i]; o.position.set(t.x + 0.5, U + 0.2, t.z + 0.5); o.scale.set(0.14, 0.42, 0.14); hl(c, t.id, "#76543a");
    }, [trees, highlight])}>
      <cylinderGeometry args={[0.22, 0.3, 1, 7]} /><meshStandardMaterial roughness={0.9} /></Instances>
    <Instances count={trees.length} fill={useCallback((i, o, c) => { const t = trees[i]; o.position.set(t.x + 0.5, U + 0.45, t.z + 0.5); hl(c, t.id, "#2f7a46"); }, [trees, highlight])}>
      <coneGeometry args={[0.42, 0.9, 7]} /><meshStandardMaterial roughness={0.92} /></Instances>
    <Instances count={trees.length} fill={useCallback((i, o, c) => { const t = trees[i]; o.position.set(t.x + 0.5, U + 0.78, t.z + 0.5); o.scale.set(0.72, 0.72, 0.72); hl(c, t.id, "#3d8b4d"); }, [trees, highlight])}>
      <coneGeometry args={[0.42, 0.9, 7]} /><meshStandardMaterial roughness={0.92} /></Instances>
    <Instances count={lights.length} fill={useCallback((i, o, c) => { const t = lights[i]; o.position.set(t.x + 0.5, U + 0.8, t.z + 0.5); hl(c, t.id, "#ffe29a"); }, [lights, highlight])}>
      <sphereGeometry args={[0.14, 8, 8]} /><meshBasicMaterial /></Instances>
    <Instances count={roads.length} fill={useCallback((i, o, c) => { const t = roads[i]; o.position.set(t.x + 0.5, U + 0.02, t.z + 0.5); o.scale.set(1, 0.04, 1); hl(c, t.id, "#464a56"); }, [roads, highlight])}>
      <boxGeometry args={[1, 1, 1]} /><meshLambertMaterial /></Instances>
    <Instances count={parks.length} fill={useCallback((i, o, c) => { const t = parks[i]; o.position.set(t.x + 1, U + 0.04, t.z + 1); o.scale.set(2, 0.08, 2); hl(c, t.id, "#5fa860"); }, [parks, highlight])}>
      <boxGeometry args={[1, 1, 1]} /><meshLambertMaterial /></Instances>
    <Instances count={parks.length} fill={useCallback((i, o, c) => { const t = parks[i]; o.position.set(t.x + 1, U + 0.17, t.z + 1); o.scale.set(0.48, 0.22, 0.48); hl(c, t.id, "#83c8d0"); }, [parks, highlight])}>
      <cylinderGeometry args={[0.38, 0.42, 1, 12]} /><meshStandardMaterial roughness={0.3} metalness={0.12} /></Instances>
  </>);
}

type Props = {
  city: City; cat: Record<string, Building>; tool: Tool; selected: string | null; rot: number;
  autoRotateView?: boolean; onViewAngle?: (angle: number) => void; lightingMode?: LightingMode;
  onPlace?: (x: number, z: number) => void; onRemove?: (id: number) => void; onExpand?: (cx: number, cz: number) => void;
};

export default function CityCanvas({ city, cat, tool, selected, rot, autoRotateView = false, onViewAngle, lightingMode = "day", onPlace, onRemove, onExpand }: Props) {
  const lighting = LIGHTING[lightingMode];
  const [hover, setHover] = useState<[number, number] | null>(null);
  const centre = useMemo(() => {
    const u = city.unlocked; const cx = u.reduce((s, c) => s + c[0], 0) / u.length, cz = u.reduce((s, c) => s + c[1], 0) / u.length;
    return [cx * 16 + 8, cz * 16 + 8] as [number, number];
  }, [city.unlocked]);
  const tileMap = useMemo(() => {
    const m = new Map<string, { t: number; open: boolean }>();
    for (const ch of city.chunks) for (let i = 0; i < ch.t.length; i++) m.set(`${ch.cx * 16 + (i % 16)},${ch.cz * 16 + Math.floor(i / 16)}`, { t: ch.t[i], open: ch.unlocked });
    return m;
  }, [city.chunks]);
  const occ = useMemo(() => {
    const m = new Map<string, number>();
    for (const it of city.items) { const b = cat[it.type]; if (b) for (const [x, z] of footprint(b, it.x, it.z, it.rot).tiles) m.set(`${x},${z}`, it.id); }
    return m;
  }, [city.items, cat]);

  const ghost = useMemo(() => {
    if (!hover || tool !== "build" || !selected || !cat[selected]) return null;
    const b = cat[selected], f = footprint(b, hover[0], hover[1], rot);
    const ok = f.tiles.every(([x, z]) => { const t = tileMap.get(`${x},${z}`); return t && t.open && (t.t === 0 || t.t === 2) && !occ.has(`${x},${z}`); });
    return { f, ok, b };
  }, [hover, tool, selected, rot, cat, tileMap, occ]);
  const hoverItem = tool === "demolish" && hover ? occ.get(`${hover[0]},${hover[1]}`) ?? null : null;

  const tileOf = (e: ThreeEvent<PointerEvent | MouseEvent>): [number, number] => [Math.floor(e.point.x), Math.floor(e.point.z)];
  return (
    <Canvas dpr={[1, 1.75]} gl={{ antialias: true, preserveDrawingBuffer: false, powerPreference: "high-performance" }}>
      <color attach="background" args={[lighting.background]} />
      <fog attach="fog" args={[lighting.fog, 105, 260]} />
      <OrthographicCamera makeDefault position={[centre[0] + 45, 45, centre[1] + 45]} zoom={15} near={-300} far={600} />
      <TownControls centre={centre} autoRotateView={autoRotateView} onViewAngle={onViewAngle ?? (() => {})} />
      <hemisphereLight args={[lighting.sky, lighting.ground, lighting.hemi]} />
      <ambientLight intensity={lighting.ambient} />
      <directionalLight position={[-30, 60, 20]} intensity={lighting.keyPower} color={lighting.key} />
      <directionalLight position={[35, 28, -35]} intensity={lighting.fillPower} color={lighting.fill} />
      <mesh position={[centre[0], -0.16, centre[1]]} rotation-x={-Math.PI / 2} receiveShadow>
        <planeGeometry args={[2000, 2000]} /><meshStandardMaterial color="#718b71" roughness={1} />
      </mesh>
      <Terrain city={city} />
      <Buildings items={city.items} cat={cat} highlight={hoverItem} night={lightingMode === "night"} />
      <Decor items={city.items} cat={cat} highlight={hoverItem} />
      {ghost && ghost.f.tiles.map(([x, z]) => (
        <mesh key={`${x},${z}`} position={[x + 0.5, U + 0.06, z + 0.5]}>
          <boxGeometry args={[0.96, 0.1, 0.96]} /><meshBasicMaterial color={ghost.ok ? "#2ea043" : "#e5484d"} transparent opacity={0.75} />
        </mesh>
      ))}
      {ghost && <BuildingModel item={{ id: -1, type: selected!, x: hover![0], z: hover![1], rot, origin: "preview" }} b={ghost.b} preview night={lightingMode === "night"} />}
      {ghost && <group position={[hover![0] + ghost.f.w / 2, U + ghost.b.h * U + 0.72, hover![1] + ghost.f.d / 2]} rotation-y={rot * Math.PI / 2}>
        <mesh position={[0, 0, -0.12]}><boxGeometry args={[0.15, 0.1, 0.3]} /><meshBasicMaterial color="#ffc84a" /></mesh>
        <mesh position={[-0.09, 0, -0.23]} rotation-y={-0.68}><boxGeometry args={[0.08, 0.1, 0.22]} /><meshBasicMaterial color="#ffc84a" /></mesh>
        <mesh position={[0.09, 0, -0.23]} rotation-y={0.68}><boxGeometry args={[0.08, 0.1, 0.22]} /><meshBasicMaterial color="#ffc84a" /></mesh>
      </group>}
      {tool === "expand" && city.expandable.map(([cx, cz]) => (
        <mesh key={`${cx},${cz}`} position={[cx * 16 + 8, 1.4, cz * 16 + 8]} rotation-x={-Math.PI / 2}
              onClick={(e) => { e.stopPropagation(); if (e.delta < 5) onExpand?.(cx, cz); }}>
          <planeGeometry args={[15.6, 15.6]} /><meshBasicMaterial color="#5B3B8C" transparent opacity={0.38} />
        </mesh>
      ))}
      <mesh position={[centre[0], U + 0.01, centre[1]]} rotation-x={-Math.PI / 2}
            onPointerMove={(e) => setHover(tileOf(e))} onPointerOut={() => setHover(null)}
            onClick={(e) => {
              if (e.delta > 5) return;
              const [x, z] = tileOf(e);
              if (tool === "build") onPlace?.(x, z);
              else if (tool === "demolish") { const id = occ.get(`${x},${z}`); if (id) onRemove?.(id); }
            }}>
        <planeGeometry args={[2000, 2000]} /><meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </Canvas>
  );
}

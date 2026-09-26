"use client";

import { Html, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import type { Group, Mesh } from "three";

import { ACTIVITY_COLOR, ACTIVITY_LABEL } from "@/lib/format";
import type { AgentSummary, Room } from "@/types/world";

import { placeAgents } from "./layout";

function Building({ room, selected, onSelect }: { room: Room; selected: boolean; onSelect: () => void }) {
  const { x, z, w, d } = room.position;
  const color = room.theme?.color ?? "#8b9cff";
  const height = room.kind === "plaza" || room.kind === "park" ? 0.15 : room.is_private ? 1.6 : 2.4;
  const [hover, setHover] = useState(false);
  return (
    <group position={[x, 0, z]}>
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow onClick={onSelect}>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial color={color} transparent opacity={selected ? 0.28 : 0.12} />
      </mesh>
      {height > 0.2 && (
        <mesh position={[0, height / 2, -d / 2 + 0.25]} castShadow onClick={onSelect} onPointerOver={() => setHover(true)} onPointerOut={() => setHover(false)}>
          <boxGeometry args={[w, height, 0.5]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={hover || selected ? 0.55 : 0.18} metalness={0.2} roughness={0.35} />
        </mesh>
      )}
      {room.kind === "park" && [[-3, -2], [3, 1], [-1, 3], [4, -3]].map(([tx, tz], i) => (
        <group key={i} position={[tx, 0, tz]}>
          <mesh position={[0, 0.6, 0]}><cylinderGeometry args={[0.12, 0.15, 1.2]} /><meshStandardMaterial color="#5b4636" /></mesh>
          <mesh position={[0, 1.6, 0]} castShadow><icosahedronGeometry args={[0.9, 0]} /><meshStandardMaterial color="#3fae7a" flatShading /></mesh>
        </group>
      ))}
      {room.kind === "plaza" && (
        <mesh position={[0, 0.4, 0]}><cylinderGeometry args={[1.8, 2.1, 0.8, 32]} /><meshStandardMaterial color="#8ea2ff" emissive="#5d6cff" emissiveIntensity={0.25} /></mesh>
      )}
      <Html position={[0, height + 1.1, -d / 2]} center distanceFactor={38} zIndexRange={[10, 0]}>
        <button onClick={onSelect} className="whitespace-nowrap rounded-full border border-white/10 bg-ink-900/80 px-3 py-1 text-[11px] font-medium text-mist-100 backdrop-blur">
          {room.name} <span className="text-mist-500">{room.occupancy}</span>
        </button>
      </Html>
    </group>
  );
}

function AgentFigure({ agent, target, onOpen }: { agent: AgentSummary; target: { x: number; z: number }; onOpen: () => void }) {
  const ref = useRef<Group>(null);
  const body = useRef<Mesh>(null);
  const act = agent.state?.activity ?? "idle";
  const color = agent.avatar?.palette?.[0] ?? "#8b9cff";
  const phase = useMemo(() => Math.random() * Math.PI * 2, []);
  useFrame((state, dt) => {
    const g = ref.current;
    if (!g) return;
    const k = 1 - Math.exp(-dt * 2.2);
    g.position.x += (target.x - g.position.x) * k;
    g.position.z += (target.z - g.position.z) * k;
    const t = state.clock.elapsedTime + phase;
    const bob = act === "walking" ? Math.abs(Math.sin(t * 8)) * 0.18 : act === "resting" ? 0 : Math.sin(t * 2) * 0.05;
    if (body.current) body.current.position.y = 0.9 + bob;
    if (act === "talking" || act === "playing") g.rotation.y = Math.sin(t * 1.5) * 0.4;
  });
  return (
    <group ref={ref} position={[target.x, 0, target.z]} onClick={(e) => { e.stopPropagation(); onOpen(); }}>
      <mesh ref={body} castShadow position={[0, 0.9, 0]}>
        <capsuleGeometry args={[0.38, act === "resting" ? 0.3 : 0.7, 6, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.25} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.5, 0.62, 32]} />
        <meshBasicMaterial color={ACTIVITY_COLOR[act]} transparent opacity={0.8} />
      </mesh>
      <Html position={[0, 2.25, 0]} center distanceFactor={26} zIndexRange={[20, 0]}>
        <div className="pointer-events-none whitespace-nowrap text-center">
          <div className="text-[12px] font-semibold text-white drop-shadow">{agent.name}</div>
          <div className="text-[10px]" style={{ color: ACTIVITY_COLOR[act] }}>{ACTIVITY_LABEL[act]}</div>
        </div>
      </Html>
    </group>
  );
}

export default function World3D({ rooms, agents, origins, selected, onSelectRoom }: {
  rooms: Room[]; agents: AgentSummary[]; origins: Map<string, string>; selected?: string | null; onSelectRoom: (slug: string) => void;
}) {
  const router = useRouter();
  const placed = placeAgents(rooms, agents, origins);
  return (
    <Canvas shadows camera={{ position: [0, 48, 58], fov: 42 }} dpr={[1, 2]} gl={{ antialias: true }}>
      <color attach="background" args={["#07080d"]} />
      <fog attach="fog" args={["#07080d", 70, 150]} />
      <ambientLight intensity={0.45} />
      <directionalLight position={[20, 40, 15]} intensity={1.1} castShadow shadow-mapSize={[1024, 1024]} />
      <pointLight position={[0, 10, 0]} intensity={40} color="#8b9cff" distance={50} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow position={[0, 0, 4]}>
        <planeGeometry args={[140, 140]} />
        <meshStandardMaterial color="#0c0f18" roughness={0.95} />
      </mesh>
      <gridHelper args={[140, 70, "#1b2030", "#11151f"]} position={[0, 0.01, 4]} />
      {rooms.map((r) => (
        <Building key={r.id} room={r} selected={selected === r.slug} onSelect={() => onSelectRoom(r.slug)} />
      ))}
      {placed.map((p) => (
        <AgentFigure key={p.agent.id} agent={p.agent} target={{ x: p.x, z: p.z }} onOpen={() => router.push(`/agents/${p.agent.slug}`)} />
      ))}
      <OrbitControls enablePan maxPolarAngle={Math.PI / 2.2} minDistance={15} maxDistance={110} target={[0, 0, 4]} />
    </Canvas>
  );
}

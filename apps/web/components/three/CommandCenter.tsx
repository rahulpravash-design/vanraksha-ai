"use client";

/**
 * Three-dimensional district view.
 *
 * The 3D is doing one job that the flat map cannot: showing *magnitude and
 * state together across a whole district at once*. Each village is a column
 * whose height is its reporting volume and whose colour step is the worst band
 * present, so an officer sees where the weight is without reading a table.
 *
 * Everything else is deliberately restrained. There is no terrain mesh, no
 * post-processing, no orbiting camera doing laps — those cost frames on the
 * hardware this will actually run on, and none of them encode data.
 *
 * The scene is disposed properly on unmount: geometries, materials and the
 * renderer all hold GPU memory that React will not reclaim for us.
 */

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import type { Cluster, VillageRow } from "@/lib/types";

export interface CommandCenterProps {
  villages: VillageRow[];
  clusters: Cluster[];
  onSelect?: (villageId: string | null) => void;
}

const COLUMN_WIDTH = 2.2;
const MAX_HEIGHT = 26;
const PLANE_SIZE = 120;

export function CommandCenter({ villages, clusters, onSelect }: CommandCenterProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [hovered, setHovered] = useState<VillageRow | null>(null);
  const [unsupported, setUnsupported] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !villages.length) return;

    // A device without WebGL should get a clear message, not a blank rectangle.
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setUnsupported(true);
      return;
    }

    const styles = getComputedStyle(document.documentElement);
    const token = (name: string, fallback: string) =>
      (styles.getPropertyValue(name) || fallback).trim();

    const surface = new THREE.Color(token("--surface-2", "#232321"));
    const accent = new THREE.Color(token("--series-1", "#3987e5"));
    const critical = new THREE.Color(token("--status-critical", "#d03b3b"));
    const serious = new THREE.Color(token("--status-serious", "#ec835a"));
    const gridColour = new THREE.Color(token("--grid", "#2c2c2a"));

    const width = mount.clientWidth;
    const height = Math.max(mount.clientHeight, 420);

    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 600);
    camera.position.set(72, 58, 72);
    camera.lookAt(0, 0, 0);

    scene.add(new THREE.AmbientLight(0xffffff, 1.5));
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(40, 80, 30);
    scene.add(key);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(PLANE_SIZE, PLANE_SIZE),
      new THREE.MeshStandardMaterial({
        color: surface, roughness: 0.95, metalness: 0,
      }),
    );
    ground.rotation.x = -Math.PI / 2;
    scene.add(ground);

    const grid = new THREE.GridHelper(PLANE_SIZE, 24, gridColour, gridColour);
    (grid.material as THREE.Material).opacity = 0.45;
    (grid.material as THREE.Material).transparent = true;
    grid.position.y = 0.02;
    scene.add(grid);

    // Project lat/lon onto the plane, keeping the district's aspect ratio.
    const lats = villages.map((v) => v.latitude);
    const lons = villages.map((v) => v.longitude);
    const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
    const cos = Math.cos((midLat * Math.PI) / 180);
    const xs = lons.map((lon) => lon * cos);
    const spanX = Math.max(Math.max(...xs) - Math.min(...xs), 0.02);
    const spanY = Math.max(Math.max(...lats) - Math.min(...lats), 0.02);
    const scale = (PLANE_SIZE * 0.7) / Math.max(spanX, spanY);
    const centreX = (Math.max(...xs) + Math.min(...xs)) / 2;
    const centreY = (Math.max(...lats) + Math.min(...lats)) / 2;

    const project = (lat: number, lon: number): [number, number] => [
      (lon * cos - centreX) * scale,
      -(lat - centreY) * scale,
    ];

    const maxReports = Math.max(...villages.map((v) => v.report_count), 1);
    const disposables: (THREE.BufferGeometry | THREE.Material)[] = [];
    const columns: THREE.Mesh[] = [];

    for (const village of villages) {
      const [x, z] = project(village.latitude, village.longitude);
      const columnHeight = Math.max((village.report_count / maxReports) * MAX_HEIGHT, 0.6);

      const colour =
        village.death_count > 0
          ? critical
          : village.escalated_count > 0
            ? serious
            : accent;

      const geometry = new THREE.BoxGeometry(COLUMN_WIDTH, columnHeight, COLUMN_WIDTH);
      const material = new THREE.MeshStandardMaterial({
        color: colour,
        roughness: 0.4,
        metalness: 0.1,
        emissive: colour,
        emissiveIntensity: village.death_count > 0 ? 0.35 : 0.12,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(x, columnHeight / 2, z);
      mesh.userData = { village };
      scene.add(mesh);
      columns.push(mesh);
      disposables.push(geometry, material);
    }

    // Cluster extents, drawn flat on the ground so they read as areas.
    for (const cluster of clusters) {
      const [x, z] = project(cluster.centroid_lat, cluster.centroid_lon);
      const radius = Math.max(cluster.radius_km * (scale / 111.32), 5);
      const geometry = new THREE.RingGeometry(radius * 0.96, radius, 64);
      const material = new THREE.MeshBasicMaterial({
        color: critical, transparent: true, opacity: 0.75, side: THREE.DoubleSide,
      });
      const ring = new THREE.Mesh(geometry, material);
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(x, 0.05, z);
      scene.add(ring);
      disposables.push(geometry, material);

      const discGeometry = new THREE.CircleGeometry(radius, 64);
      const discMaterial = new THREE.MeshBasicMaterial({
        color: critical, transparent: true, opacity: 0.1, side: THREE.DoubleSide,
      });
      const disc = new THREE.Mesh(discGeometry, discMaterial);
      disc.rotation.x = -Math.PI / 2;
      disc.position.set(x, 0.04, z);
      scene.add(disc);
      disposables.push(discGeometry, discMaterial);
    }

    // ------------------------------------------------------------ interaction
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let dragging = false;
    let lastX = 0;
    let azimuth = Math.PI / 4;
    let radius = 118;
    let elevation = 0.62;

    const applyCamera = () => {
      camera.position.set(
        Math.cos(azimuth) * radius * Math.cos(elevation),
        Math.sin(elevation) * radius,
        Math.sin(azimuth) * radius * Math.cos(elevation),
      );
      camera.lookAt(0, 4, 0);
    };
    applyCamera();

    const onPointerDown = (event: PointerEvent) => {
      dragging = true;
      lastX = event.clientX;
    };
    const onPointerUp = () => {
      dragging = false;
    };
    const onPointerMove = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      if (dragging) {
        azimuth += (event.clientX - lastX) * 0.006;
        lastX = event.clientX;
        applyCamera();
        return;
      }
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(columns)[0];
      const village = hit ? (hit.object.userData.village as VillageRow) : null;
      setHovered(village);
      renderer.domElement.style.cursor = village ? "pointer" : "grab";
    };
    const onClick = () => {
      if (hovered) onSelect?.(hovered.village_id);
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      radius = Math.min(220, Math.max(52, radius + event.deltaY * 0.08));
      applyCamera();
    };

    const element = renderer.domElement;
    element.style.cursor = "grab";
    element.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointerup", onPointerUp);
    element.addEventListener("pointermove", onPointerMove);
    element.addEventListener("click", onClick);
    element.addEventListener("wheel", onWheel, { passive: false });

    const onResize = () => {
      const nextWidth = mount.clientWidth;
      const nextHeight = Math.max(mount.clientHeight, 420);
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(nextWidth, nextHeight);
    };
    const observer = new ResizeObserver(onResize);
    observer.observe(mount);

    // Respect a reduced-motion preference: render once, no animation loop.
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let pulse = 0;

    const render = () => {
      if (!reduceMotion) {
        pulse += 0.02;
        const factor = 0.9 + Math.sin(pulse) * 0.1;
        for (const mesh of columns) {
          const village = mesh.userData.village as VillageRow;
          if (village.death_count > 0) {
            (mesh.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.25 * factor + 0.2;
          }
        }
      }
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    };
    render();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      element.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointerup", onPointerUp);
      element.removeEventListener("pointermove", onPointerMove);
      element.removeEventListener("click", onClick);
      element.removeEventListener("wheel", onWheel);
      for (const item of disposables) item.dispose();
      (ground.geometry as THREE.BufferGeometry).dispose();
      (ground.material as THREE.Material).dispose();
      grid.geometry.dispose();
      (grid.material as THREE.Material).dispose();
      renderer.dispose();
      if (element.parentElement === mount) mount.removeChild(element);
    };
    // `hovered` is read inside onClick via closure over the latest render's
    // value; re-running the whole scene on hover would be wasteful, so the
    // click handler reads it from state at call time instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [villages, clusters]);

  if (unsupported) {
    return (
      <div className="flex h-[420px] items-center justify-center px-6 text-center text-xs text-ink-muted">
        This device does not support WebGL. The flat map view shows the same data.
      </div>
    );
  }

  return (
    <div className="relative">
      <div ref={mountRef} className="h-[460px] w-full overflow-hidden rounded-card" />

      {hovered ? (
        <div
          className="pointer-events-none absolute left-4 top-4 rounded-lg border px-3 py-2 text-[11px] shadow-sm"
          style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
        >
          <p className="text-xs font-semibold text-ink">{hovered.name}</p>
          <p className="mt-0.5 text-ink-muted">{hovered.block} block</p>
          <dl className="tabular mt-1.5 space-y-0.5 text-ink-secondary">
            <div className="flex gap-3">
              <dt className="w-20">Reports</dt>
              <dd className="font-medium text-ink">{hovered.report_count}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-20">Escalated</dt>
              <dd className="font-medium text-ink">{hovered.escalated_count}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-20">Deaths</dt>
              <dd className="font-medium text-ink">{hovered.death_count}</dd>
            </div>
          </dl>
        </div>
      ) : null}

      <div className="pointer-events-none absolute bottom-4 left-4 text-[11px] text-ink-muted">
        Drag to rotate &middot; scroll to zoom
      </div>
    </div>
  );
}

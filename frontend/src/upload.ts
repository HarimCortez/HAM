/**
 * R9 "Add photos and videos" (docs/ux/intake.md; design-system/screens/intake.md C§24).
 *
 * Progressive enhancement over a plain `<input type="file">`: reserves one presigned-PUT slot
 * per chosen file from the server (`POST .../media/reserve`), PUTs the bytes straight to
 * object storage (never through Django, PRD §70.2 "core pages load in ~2s" — large uploads
 * never touch the app server), then tells the server the upload finished
 * (`POST <complete_url>`) so `ham.media.services.complete_upload` can re-check it and enqueue
 * processing. Each tile shows progress via `XMLHttpRequest.upload.onprogress` (the `fetch`
 * API has no upload-progress event as of this writing) and offers **Retry** on failure — no
 * heavy upload library (CLAUDE.md "avoid heavy libraries for simple needs").
 *
 * Accessible status: a single `aria-live="polite"` region announces "n of m uploaded" rather
 * than each tile's progress percentage on every tick (design-system C§24 "polite live region
 * with 'n of m uploaded'").
 */

interface ReserveFile {
  media_kind: "photo" | "video";
  content_type: string;
  declared_bytes: number;
}

interface ReservedFile {
  item_id: string;
  media_kind: string;
  put_url: string;
  content_type: string;
  complete_url: string;
}

interface ReserveResponse {
  files?: ReservedFile[];
  error?: string;
}

type TileStatus = "waiting" | "uploading" | "uploaded" | "failed" | "removed";

interface TileState {
  file: File;
  mediaKind: "photo" | "video";
  status: TileStatus;
  progress: number;
  reserved?: ReservedFile;
  errorMessage?: string;
  el: HTMLLIElement;
}

const MAX_RETRIES_MESSAGE = "Couldn't upload";

function isVideo(file: File): boolean {
  return file.type.startsWith("video/");
}

function formatSummary(uploaded: number, total: number): string {
  return `${uploaded} of ${total} uploaded`;
}

class UploadGrid {
  private root: HTMLElement;
  private grid: HTMLUListElement;
  private summaryCount: HTMLElement;
  private liveRegion: HTMLElement;
  private reserveUrl: string;
  private tiles: TileState[] = [];
  private photoCount = 0;
  private videoCount = 0;
  private maxPhotos: number;
  private maxVideos: number;
  private photoTypes: string[];
  private videoTypes: string[];

  constructor(root: HTMLElement) {
    this.root = root;
    this.grid = root.querySelector<HTMLUListElement>("[data-upload-grid]")!;
    this.summaryCount = root.querySelector<HTMLElement>("[data-upload-summary]")!;
    this.liveRegion = root.querySelector<HTMLElement>("[data-upload-live]")!;
    this.reserveUrl = root.dataset.reserveUrl ?? "";
    this.maxPhotos = Number(root.dataset.maxPhotos ?? "10");
    this.maxVideos = Number(root.dataset.maxVideos ?? "3");
    this.photoTypes = (root.dataset.photoTypes ?? "").split(",").filter(Boolean);
    this.videoTypes = (root.dataset.videoTypes ?? "").split(",").filter(Boolean);

    const fileInputs = root.querySelectorAll<HTMLInputElement>("[data-upload-input]");
    fileInputs.forEach((input) => {
      input.addEventListener("change", () => {
        if (input.files) this.addFiles(Array.from(input.files));
        input.value = "";
      });
    });

    this.updateSummary();
  }

  private acceptedType(file: File): boolean {
    return isVideo(file) ? this.videoTypes.includes(file.type) : this.photoTypes.includes(file.type);
  }

  private addFiles(files: File[]): void {
    for (const file of files) {
      const mediaKind: "photo" | "video" = isVideo(file) ? "video" : "photo";
      if (!this.acceptedType(file)) {
        this.addRejectedTile(file, "That file type isn't supported.");
        continue;
      }
      if (mediaKind === "photo" && this.photoCount >= this.maxPhotos) {
        this.addRejectedTile(file, `You can add up to ${this.maxPhotos} photos.`);
        continue;
      }
      if (mediaKind === "video" && this.videoCount >= this.maxVideos) {
        this.addRejectedTile(file, `You can add up to ${this.maxVideos} videos.`);
        continue;
      }
      if (mediaKind === "photo") this.photoCount += 1;
      else this.videoCount += 1;

      const tile = this.buildTile(file, mediaKind);
      this.tiles.push(tile);
      this.grid.appendChild(tile.el);
    }
    this.updateSummary();
    void this.reserveAndUpload(this.tiles.filter((t) => t.status === "waiting"));
  }

  private addRejectedTile(file: File, message: string): void {
    const el = document.createElement("li");
    el.className = "upload-tile upload-tile--rejected";
    el.innerHTML = `<div class="upload-tile__status"><span>${escapeHtml(file.name)}</span><span>${escapeHtml(message)}</span></div>`;
    this.grid.appendChild(el);
  }

  private buildTile(file: File, mediaKind: "photo" | "video"): TileState {
    const el = document.createElement("li");
    el.className = "upload-tile";
    const objectUrl = URL.createObjectURL(file);
    el.innerHTML = `
      <div class="upload-tile__thumb">
        ${mediaKind === "photo" ? `<img src="${objectUrl}" alt="">` : `<span aria-hidden="true">&#9654;</span>`}
      </div>
      <div class="upload-tile__status" data-status>Waiting to upload</div>
      <button type="button" class="upload-tile__remove" aria-label="Remove ${escapeHtml(file.name)}" data-remove hidden>&times;</button>
    `;
    const tile: TileState = { file, mediaKind, status: "waiting", progress: 0, el };
    el.querySelector<HTMLButtonElement>("[data-remove]")?.addEventListener("click", () => {
      this.removeTile(tile);
    });
    return tile;
  }

  private updateTileStatus(tile: TileState): void {
    const statusEl = tile.el.querySelector<HTMLElement>("[data-status]");
    if (!statusEl) return;
    if (tile.status === "waiting") statusEl.textContent = "Waiting to upload";
    else if (tile.status === "uploading") statusEl.textContent = `Uploading ${tile.progress}%`;
    else if (tile.status === "uploaded") statusEl.textContent = "Uploaded";
    else if (tile.status === "failed") {
      statusEl.innerHTML = "";
      statusEl.append(`${MAX_RETRIES_MESSAGE}. `);
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Retry";
      retry.className = "link-button";
      retry.addEventListener("click", () => void this.reserveAndUpload([tile]));
      statusEl.append(retry);
    }
    const removeBtn = tile.el.querySelector<HTMLButtonElement>("[data-remove]");
    if (removeBtn) removeBtn.hidden = tile.status !== "uploaded";
  }

  private updateSummary(): void {
    const uploaded = this.tiles.filter((t) => t.status === "uploaded").length;
    this.summaryCount.textContent = `${this.photoCount} of ${this.maxPhotos} photos · ${this.videoCount} of ${this.maxVideos} videos`;
    this.liveRegion.textContent = formatSummary(uploaded, this.tiles.length);
  }

  private removeTile(tile: TileState): void {
    tile.status = "removed";
    tile.el.remove();
    this.tiles = this.tiles.filter((t) => t !== tile);
    if (tile.mediaKind === "photo") this.photoCount -= 1;
    else this.videoCount -= 1;
    this.updateSummary();
  }

  private async reserveAndUpload(tiles: TileState[]): Promise<void> {
    if (tiles.length === 0) return;
    tiles.forEach((t) => {
      t.status = "uploading";
      this.updateTileStatus(t);
    });

    let reservedFiles: ReservedFile[];
    try {
      const body: { files: ReserveFile[] } = {
        files: tiles.map((t) => ({
          media_kind: t.mediaKind,
          content_type: t.file.type,
          declared_bytes: t.file.size,
        })),
      };
      const response = await fetch(this.reserveUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(body),
      });
      const data: ReserveResponse = await response.json();
      if (!response.ok || !data.files) {
        throw new Error(data.error ?? "Couldn't reserve an upload slot.");
      }
      reservedFiles = data.files;
    } catch {
      tiles.forEach((t) => {
        t.status = "failed";
        this.updateTileStatus(t);
      });
      this.updateSummary();
      return;
    }

    await Promise.all(
      tiles.map((tile, index) => this.uploadOne(tile, reservedFiles[index])),
    );
  }

  private uploadOne(tile: TileState, reserved: ReservedFile | undefined): Promise<void> {
    return new Promise((resolve) => {
      if (!reserved) {
        tile.status = "failed";
        this.updateTileStatus(tile);
        this.updateSummary();
        resolve();
        return;
      }
      tile.reserved = reserved;
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", reserved.put_url);
      xhr.setRequestHeader("Content-Type", reserved.content_type);
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          tile.progress = Math.round((event.loaded / event.total) * 100);
          this.updateTileStatus(tile);
        }
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          void this.completeUpload(tile, reserved).then(resolve);
        } else {
          tile.status = "failed";
          this.updateTileStatus(tile);
          this.updateSummary();
          resolve();
        }
      });
      xhr.addEventListener("error", () => {
        tile.status = "failed";
        this.updateTileStatus(tile);
        this.updateSummary();
        resolve();
      });
      xhr.send(tile.file);
    });
  }

  private async completeUpload(tile: TileState, reserved: ReservedFile): Promise<void> {
    try {
      const response = await fetch(reserved.complete_url, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
      });
      if (!response.ok) throw new Error("complete failed");
      tile.status = "uploaded";
    } catch {
      tile.status = "failed";
    }
    this.updateTileStatus(tile);
    this.updateSummary();
  }
}

function escapeHtml(value: string): string {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

function init(): void {
  document.querySelectorAll<HTMLElement>("[data-upload-root]").forEach((root) => {
    new UploadGrid(root);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

export {};

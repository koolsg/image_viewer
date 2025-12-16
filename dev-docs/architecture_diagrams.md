# Image Viewer Project Architecture

This document visualizes the structure and data flow of the `image_viewer` project, reflecting the current codebase state as of Dec 2025.

## 1. System Architecture Overview

This flowchart illustrates how the UI decouples from the backend operations using the `ImageEngine` and various background workers.

```mermaid
graph TD
    %% Define Styles
    classDef ui fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef engine fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef worker fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    classDef storage fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;

    subgraph UI_Layer [UI Layer - Main Thread]
        Viewer[ImageViewer<br/>Main Window]:::ui
        Explorer[ThumbnailGridWidget<br/>Explorer Mode]:::ui
        Canvas[ImageCanvas<br/>View Mode]:::ui
    end

    subgraph Core_Engine [Core Engine]
        Engine[ImageEngine<br/>Controller]:::engine
        FS_Model[ImageFileSystemModel<br/>Data Model]:::engine
        ThumbCache[InMemory Cache<br/>_thumb_cache]:::engine
    end

    subgraph Background_Workers [Background Workers]
        DirWorker[DirectoryWorker<br/>File Scanning]:::worker
        DBWorker[FSDBLoadWorker<br/>DB & Meta Loading]:::worker
        Loader[Loader<br/>ProcessPoolExecutor]:::worker
        Decoder[pyvips Decoder]:::worker
        Convert[ConvertWorker<br/>QImage Generation]:::worker
    end

    subgraph Persistence [Persistence]
        FileSystem[(File System)]:::storage
        SQLite[(ThumbDB)]:::storage
    end

    %% Relationships
    Viewer -->|Uses| Engine
    Viewer -->|Contains| Explorer
    Viewer -->|Contains| Canvas

    Explorer -->|Binds to| FS_Model
    Engine -->|Owns| FS_Model
    Engine -->|Owns| Loader
    Engine -->|Owns| DirWorker

    FS_Model -->|Owns| DBWorker
    FS_Model -->|Uses| ThumbCache

    %% Data Flow
    Engine -->|Start Scan| DirWorker
    DirWorker -->|File List| Engine

    FS_Model -->|Start Load| DBWorker
    DBWorker -->|Query| SQLite
    DBWorker -->|Stat| FileSystem

    DBWorker -->|Found Thumbs| FS_Model
    DBWorker -->|Missing Path, Meta| FS_Model

    FS_Model -->|Request Decode| Loader
    Loader -->|Decode| Decoder
    Decoder -->|Raw Data| Convert
    Convert -->|QPixmap| Engine
    Engine -->|Signal| Canvas
```

---

## 2. Sequence Diagram: Open Folder (Async Loading)

This diagram details the sequence when a user opens a folder. It highlights the optimizations made to prevent UI freezing by offloading I/O and metadata reading to the `FSDBLoadWorker`.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Viewer as ImageViewer
    participant Engine as ImageEngine
    participant DirWorker as DirectoryWorker
    participant Model as ImageFileSystemModel
    participant DBWorker as FSDBLoadWorker
    participant Loader as Loader

    User->>Viewer: Open Folder
    Viewer->>Engine: open_folder(path)

    %% Step 1: File Listing (Async)
    Note over Engine, DirWorker: 1. Async File Listing
    Engine->>DirWorker: run(path)
    activate DirWorker
    DirWorker-->>Engine: files_ready (List[str])
    deactivate DirWorker

    Engine->>Viewer: folder_changed signal
    Viewer->>Model: setRootPath(path)
    Viewer->>Model: batch_load_thumbnails()

    %% Step 2: DB & Meta Loading (Async)
    Note over Model, DBWorker: 2. Async DB & Meta Loading
    Model->>DBWorker: run()
    activate DBWorker

    Note right of DBWorker: Iterates files in thread. Performs stat() and DB query. Compares mtime/size.

    %% Scenario A: Thumb exists in DB
    DBWorker-->>Model: chunk_loaded (List[Dict])
    Model->>Model: Update _meta & _thumb_cache
    Model-->>Viewer: dataChanged (Show Thumb)

    %% Scenario B: Thumb missing or changed
    Note right of DBWorker: New Feature: Passes (path, mtime, size) to avoid main thread stat()
    DBWorker-->>Model: missing_paths (List[Tuple])

    Model->>Model: Update _meta immediately
    Model->>Loader: request_load(path) (Async Decode)

    deactivate DBWorker

    %% Step 3: Decode & Display
    Loader-->>Model: image_decoded
    Model->>Model: Update _thumb_cache
    Model-->>Viewer: dataChanged (Show New Thumb)
```

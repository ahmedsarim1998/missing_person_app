# Missing Person App - Technical Summary

This document provides a comprehensive technical summary of the "Missing Person App". It details the system architecture, data flow, libraries, and database schema to assist in generating DFDs, ERDs, Use Case diagrams, and UML diagrams.

## 1. System Overview

The application is a full-stack web based solution designed to help locate missing persons using facial recognition technology. It allows users to report missing persons by uploading photos and details. The system then monitors a live video feed (simulated or real camera) to detect faces in real-time and match them against the database of reported missing persons. Administrators can review and confirm these matches.

### Key Modules:
-   **Frontend**: A responsive React application for user interaction (reporting, viewing, admin dashboard).
-   **Backend**: A Flask API that handles authentication, data management, and image processing.
-   **AI Engine**: A computer vision module using MTCNN for face detection and FaceNet for generating face embeddings to perform similarity matching.

---

## 2. Technology Stack & Libraries

### Backend (Python/Flask)
| Library | Purpose |
| :--- | :--- |
| **flask** | Main web framework for the API. |
| **flask-sqlalchemy** | ORM for database interactions (SQLite). |
| **flask-cors** | Handles Cross-Origin Resource Sharing (allows frontend to talk to backend). |
| **flask-jwt-extended** | Handles JSON Web Token (JWT) based authentication. |
| **werkzeug** | Utilities for secure password hashing and filename handling. |
| **opencv-python-headless** | Used for image processing (reading, resizing, drawing boxes) and video capture. |
| **mtcnn** | **Multi-task Cascaded Convolutional Networks**. Used for detecting faces in images and video frames. |
| **keras-facenet** | Pre-trained model used to generate 128-dimensional embeddings (vectors) from face images. |
| **tensorflow** | Underlying ML engine for Keras/FaceNet. |
| **numpy** | Efficient numerical operations, specifically for calculating Euclidean distances between embeddings. |

### Frontend (JavaScript/React)
| Library | Purpose |
| :--- | :--- |
| **react** | UI library for building the interface components. |
| **vite** | Build tool and development server (faster than CRA). |
| **react-router-dom** | Client-side routing (handling navigation between pages). |
| **axios** | HTTP client for making API requests to the Flask backend. |
| **tailwindcss** | Utility-first CSS framework for styling. |
| **lucide-react** | Icon library. |

---

## 3. Data Flow & Process Logic

This section describes how data moves through the system, useful for DFDs and Flowcharts.

### A. User Authentication (Login/Signup)
1.  **User** sends credentials (username/password) via Frontend.
2.  **API** (`/api/auth/login`) verifies hash against **Database**.
3.  **API** returns a **JWT Token**.
4.  **Frontend** stores token and uses it for subsequent authenticated requests.

### B. Reporting a Missing Person
1.  **User** fills a form (Name, National ID, Photos) on the Frontend.
2.  **Frontend** sends `POST /api/cases` with `multipart/form-data`.
3.  **Backend Processing**:
    *   Validates input (National ID format).
    *   Saves images to `/static/uploads`.
    *   **Face Detection**: Uses `MTCNN` to find faces in the uploaded photos.
    *   **Feature Extraction**: Uses `FaceNet` to generate a 128-d embedding for the detected face.
    *   **Storage**: Creates a `MissingPerson` record in the **Database**, storing the personal info and the serialized embedding (blob).

### C. Live Stream & Matching (The AI Core)
1.  **User** accesses the 'Stream' page.
2.  **Frontend** requests `/api/stream/feed`.
3.  **Backend** starts a video capture loop (`gen_frames`):
    *   **Capture**: Reads a frame from the camera.
    *   **Detect**: `MTCNN` finds all faces in the current frame.
    *   **Embed**: `FaceNet` converts each face into an embedding.
    *   **Compare**: The system queries *all* 'active' `MissingPerson` records from the **Database**.
    *   **Calculate**: Computes **Euclidean Distance** between the live face and stored embeddings.
    *   **Match Logic**: If `Distance < 0.65` (Threshold), it is considered a **Match**.
    *   **Alert**: A `MatchAlert` record is created in the **Database** with status 'pending'.
    *   **visualize**: Draws a Bounding Box (Green for match, Red for unknown) and Label on the frame.
4.  **Backend** yields the processed frame as a MJPEG stream to the **Frontend**.

### D. Admin Review
1.  **Admin** views Dashboard (`GET /api/admin/dashboard` & `/api/admin/matches`).
2.  **Backend** queries `MatchAlert` table for 'pending' matches.
3.  **Admin** confirms or rejects a match (`POST /api/admin/match/<id>`).
4.  **Backend** updates `MatchAlert` status in the **Database**.

---

## 4. Database Schema (For ERD)

The system uses a relational database (SQLite via SQLAlchemy).

### Tables & Attributes:

#### 1. User
*   **id** (PK, Integer): Unique identifier.
*   **username** (String): Unique login name.
*   **email** (String): Unique email.
*   **password_hash** (String): Hashed password.
*   **role** (String): 'admin' or 'user'.
*   **first_name**, **last_name**, **middle_name** (String).

#### 2. MissingPerson
*   **id** (PK, Integer): Unique case ID.
*   **name** (String): Name of the missing person.
*   **national_id** (String): Unique Government ID (e.g., XXXXX-XXXXXXX-X).
*   **last_location** (String): Last known location.
*   **identifiers** (Text): Physical description/marks.
*   **status** (String): 'active' or 'solved'.
*   **created_at** (DateTime): Timestamp of report.
*   **photo_path** (String): Path to the main display photo.
*   **embedding_blob** (PickleType/Blob): Serialized list of face embeddings (NumPy arrays).

#### 3. MatchAlert
*   **id** (PK, Integer): Unique alert ID.
*   **missing_person_id** (FK, Integer): Links to `MissingPerson.id`.
*   **timestamp** (DateTime): Time of detection.
*   **confidence** (Float): Distance score (lower is better check logic, usually represented as confidence in UI).
*   **status** (String): 'pending', 'confirmed', 'rejected'.

---

## 5. Use Case Descriptions (For UML Use Case Diagram)

### Actor: Public User
*   **Register/Login**: Create an account to report cases.
*   **Report Missing Person**: Upload data and photos to the system.
*   **View Cases**: Browse public directory of missing persons.
*   **View Stream**: Watch the surveillance feed (permissions permitting).

### Actor: Administrator
*   **Login**: Access admin privileges.
*   **View Dashboard**: See statistics (Total cases, Active cases, Pending alerts).
*   **Review Matches**: specific interface to see side-by-side comparison of Live Match vs Stored Photo.
*   **Resolve Alert**: Confirm that a detected person is indeed the missing person (or reject false positives).
*   **Manage Cases**: Update status of cases (e.g., mark as 'solved').

---

## 6. Logic for Flowcharts (Code Level)

### Face Matching Algorithm ( `backend/routes/stream.py` )
1.  **Start** Frame Loop.
2.  **Input**: Get Frame from Camera.
3.  **Process**: Is `frame_count % 10 == 0`? (Optimization to skip frames).
    *   No: Skip to Encode.
    *   Yes:
        1.  `model.detect_faces(frame)` -> Returns list of bounding boxes.
        2.  **ForEach** Face:
            1.  `model.extract_face(box)` -> Crop & Resize to 160x160.
            2.  `model.get_embedding(face_img)` -> Returns 128-d Vector.
            3.  **Search**: Fetch all active `MissingPerson` embeddings.
            4.  **Compare**: Calculate `Linear Algebra Norm` (Euclidean Distance).
            5.  **Decision**:
                *   `If Distance < 0.65`: **MATCH FOUND**. Create `MatchAlert`. Set Color = Green.
                *   `Else`: **UNKNOWN**. Set Color = Red.
        3.  Draw Box & Label on Frame.
4.  **Encode**: Convert Frame to JPEG bytes.
5.  **Output**: Yield frame to response stream.
6.  **Loop**: Go to Step 2.

import numpy as np
import cv2

class FaceModel:
    _instance = None

    @staticmethod
    def get_instance():
        if FaceModel._instance is None:
            FaceModel._instance = FaceModel()
        return FaceModel._instance

    def __init__(self):
        # Heavy ML deps are imported lazily here (not at module load) so that
        # importing the blueprints / running the test suite does not pull in
        # TensorFlow. They are only loaded the first time a face is processed.
        from keras_facenet import FaceNet
        from mtcnn import MTCNN
        self.embedder = FaceNet()
        self.detector = MTCNN()

    def detect_faces(self, image):
        if image.ndim == 3 and image.shape[2] == 3:
            pass
        return self.detector.detect_faces(image)

    def extract_face(self, image, box, required_size=(160, 160)):
        x, y, width, height = box
        x1, y1 = abs(x), abs(y)
        x2, y2 = x1 + width, y1 + height
        face = image[y1:y2, x1:x2]
        if face.size == 0: return np.array([])
        face_image = cv2.resize(face, required_size)
        return face_image

    def get_embedding(self, face_image):
        face_pixels = face_image.astype('float32')
        samples = np.expand_dims(face_pixels, axis=0)
        yhat = self.embedder.embeddings(samples)
        return yhat[0]

    def distance(self, embedding1, embedding2):
        return np.linalg.norm(embedding1 - embedding2)

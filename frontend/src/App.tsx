import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import Navigation from "./components/Navigation";
import AReg800aPlayer from "./components/AReg800aPlayer";
import TCV907Page from "./components/TCV907Page";

export default function App() {
  return (
    <Router>
      <Navigation />
      <Routes>
        <Route path="/areg800a" element={<AReg800aPlayer />} />
        <Route path="/tcv907" element={<TCV907Page />} />
        <Route path="/" element={<Navigate to="/areg800a" replace />} />
      </Routes>
    </Router>
  );
}


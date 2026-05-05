package apiqueries;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.stream.Collectors;

import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;

import org.eclipse.viatra.query.runtime.api.ViatraQueryEngine;
import org.eclipse.viatra.query.runtime.emf.EMFScope;
import org.eclipse.viatra.transformation.runtime.emf.rules.batch.BatchTransformationRule;
import org.eclipse.viatra.transformation.runtime.emf.rules.batch.BatchTransformationRuleFactory;
import org.eclipse.viatra.transformation.runtime.emf.transformation.batch.BatchTransformation;
import org.eclipse.viatra.transformation.runtime.emf.transformation.batch.BatchTransformationStatements;

// Model Imports
import scenegraph.Scene;
import scenegraph.Edge;
import scenegraph.Vehicle;
import scenegraph.RoadSegment;
import scenegraph.SceneGraphModelFactory;

// Query Imports
import queries.NearCollision;
import queries.SuperNear;
import queries.VeryNear;
import queries.Near;
import queries.VisibleDistance;
import queries.RemoveEdge;
import queries.FrontRight;
import queries.RightFront;
import queries.RightRear;
import queries.RearRight;
import queries.RearLeft;
import queries.LeftRear;
import queries.LeftFront;
import queries.FrontLeft;
import queries.VehicleOnLane;
import queries.RssLongitudinalViolation;
import queries.RemoveRssLongitudinalViolation;
import queries.RssLateralViolation;
import queries.RemoveRssLateralViolation;
import queries.RemoveVehicleOnLane;

public class QueryRunner implements IApplication {

    private static final String MODEL_PATH =
            "C:\\Users\\marko\\Documents\\CAS782_Project_MB_RG\\data\\stream\\latest_snapshot.xmi";
        private static final Path MODEL_FILE = Paths.get(MODEL_PATH);
    private static final Path FLAG_DIR =
            Paths.get("C:\\Users\\marko\\Documents\\CAS782_Project_MB_RG\\data\\stream");
    private static final Path READY_FLAG = FLAG_DIR.resolve("ready_for_viatra.seq");
    private static final Path DONE_FLAG = FLAG_DIR.resolve("viatra_done.seq");

    @Override
    public Object start(IApplicationContext context) throws Exception {

        BatchTransformationRuleFactory ruleFactory = new BatchTransformationRuleFactory();

        // Near Collision
        BatchTransformationRule<NearCollision.Match, NearCollision.Matcher> nearCollisionRule =
            ruleFactory.createRule(NearCollision.instance())
            .name("NearCollisionRule")
            .action(match -> applyDistance(match.getO1(), match.getO2(), "NearCollision"))
            .build();

        // Super Near
        BatchTransformationRule<SuperNear.Match, SuperNear.Matcher> superNearRule =
            ruleFactory.createRule(SuperNear.instance())
            .name("SuperNearRule")
            .action(match -> applyDistance(match.getO1(), match.getO2(), "SuperNear"))
            .build();

        // Very Near
        BatchTransformationRule<VeryNear.Match, VeryNear.Matcher> veryNearRule =
            ruleFactory.createRule(VeryNear.instance())
            .name("VeryNearRule")
            .action(match -> applyDistance(match.getO1(), match.getO2(), "VeryNear"))
            .build();

        // Near
        BatchTransformationRule<Near.Match, Near.Matcher> nearRule =
            ruleFactory.createRule(Near.instance())
            .name("NearRule")
            .action(match -> applyDistance(match.getO1(), match.getO2(), "Near"))
            .build();

        // Visible
        BatchTransformationRule<VisibleDistance.Match, VisibleDistance.Matcher> visibleRule =
            ruleFactory.createRule(VisibleDistance.instance())
            .name("VisibleRule")
            .action(match -> applyDistance(match.getO1(), match.getO2(), "Visible"))
            .build();

        // Remove Edge
        BatchTransformationRule<RemoveEdge.Match, RemoveEdge.Matcher> removeRule =
            ruleFactory.createRule(RemoveEdge.instance())
            .name("RemoveEdgeRule")
            .action(match -> {
                Vehicle v1 = match.getO1();
                Vehicle v2 = match.getO2();
                Scene scene = (Scene) v1.eContainer();

                List<Edge> toRemove = scene.getEdges().stream()
                    .filter(e -> "vehicle".equals(e.getType()))
                    .filter(e -> (e.getSource() == v1 && e.getTarget() == v2) ||
                                 (e.getSource() == v2 && e.getTarget() == v1))
                    .collect(Collectors.toList());

                toRemove.forEach(e -> {
                    scene.getEdges().remove(e);
                    System.out.println("Removed edge: " +
                        e.getSource().getId() + " <-> " + e.getTarget().getId());
                });
            })
            .build();

        // Front Right
        BatchTransformationRule<FrontRight.Match, FrontRight.Matcher> frontRightRule =
            ruleFactory.createRule(FrontRight.instance())
            .name("FrontRightRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "FrontRight"))
            .build();

        // Right Front
        BatchTransformationRule<RightFront.Match, RightFront.Matcher> rightFrontRule =
            ruleFactory.createRule(RightFront.instance())
            .name("RightFrontRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "RightFront"))
            .build();

        // Right Rear
        BatchTransformationRule<RightRear.Match, RightRear.Matcher> rightRearRule =
            ruleFactory.createRule(RightRear.instance())
            .name("RightRearRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "RightRear"))
            .build();

        // Rear Right
        BatchTransformationRule<RearRight.Match, RearRight.Matcher> rearRightRule =
            ruleFactory.createRule(RearRight.instance())
            .name("RearRightRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "RearRight"))
            .build();

        // Rear Left
        BatchTransformationRule<RearLeft.Match, RearLeft.Matcher> rearLeftRule =
            ruleFactory.createRule(RearLeft.instance())
            .name("RearLeftRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "RearLeft"))
            .build();

        // Left Rear
        BatchTransformationRule<LeftRear.Match, LeftRear.Matcher> leftRearRule =
            ruleFactory.createRule(LeftRear.instance())
            .name("LeftRearRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "LeftRear"))
            .build();

        // Left Front
        BatchTransformationRule<LeftFront.Match, LeftFront.Matcher> leftFrontRule =
            ruleFactory.createRule(LeftFront.instance())
            .name("LeftFrontRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "LeftFront"))
            .build();

        // Front Left
        BatchTransformationRule<FrontLeft.Match, FrontLeft.Matcher> frontLeftRule =
            ruleFactory.createRule(FrontLeft.instance())
            .name("FrontLeftRule")
            .action(match -> applySpatial(match.getSource(), match.getTarget(), "FrontLeft"))
            .build();

        // Vehicle on Lane
        BatchTransformationRule<VehicleOnLane.Match, VehicleOnLane.Matcher> vehicleOnLaneRule =
            ruleFactory.createRule(VehicleOnLane.instance())
            .name("VehicleOnLaneRule")
            .action(match -> applyLane(match.getVehicle(), match.getLane()))
            .build();

        // Remove stale lane edges where the vehicle is no longer in lane bounds
        BatchTransformationRule<RemoveVehicleOnLane.Match, RemoveVehicleOnLane.Matcher> removeVehicleOnLaneRule =
            ruleFactory.createRule(RemoveVehicleOnLane.instance())
            .name("RemoveVehicleOnLaneRule")
            .action(match -> removeLane(match.getVehicle(), match.getLane()))
            .build();

        // RSS Longitudinal Violation
        BatchTransformationRule<RssLongitudinalViolation.Match, RssLongitudinalViolation.Matcher> rssLonRule =
            ruleFactory.createRule(RssLongitudinalViolation.instance())
            .name("RssLongitudinalViolationRule")
            .action(match -> applyRssEdge(match.getEgo(), match.getOther(), "rss_longitudinal"))
            .build();

        // Remove stale RSS longitudinal edge
        BatchTransformationRule<RemoveRssLongitudinalViolation.Match, RemoveRssLongitudinalViolation.Matcher> removeRssLonRule =
            ruleFactory.createRule(RemoveRssLongitudinalViolation.instance())
            .name("RemoveRssLongitudinalViolationRule")
            .action(match -> removeRssEdge(match.getEgo(), match.getOther(), "rss_longitudinal"))
            .build();

        // RSS Lateral Violation
        BatchTransformationRule<RssLateralViolation.Match, RssLateralViolation.Matcher> rssLatRule =
            ruleFactory.createRule(RssLateralViolation.instance())
            .name("RssLateralViolationRule")
            .action(match -> applyRssEdge(match.getEgo(), match.getOther(), "rss_lateral"))
            .build();

        // Remove stale RSS lateral edge
        BatchTransformationRule<RemoveRssLateralViolation.Match, RemoveRssLateralViolation.Matcher> removeRssLatRule =
            ruleFactory.createRule(RemoveRssLateralViolation.instance())
            .name("RemoveRssLateralViolationRule")
            .action(match -> removeRssEdge(match.getEgo(), match.getOther(), "rss_lateral"))
            .build();

        // 
        // Main loop
        long lastProcessedTick = 0L;
        while (true) {
            long start = System.nanoTime();
            long deadline = start + 10_000_000_000L;  // 10 seconds

            // Wait for bridge to signal new data is ready
            long readyTick = -1L;
            boolean foundReady = false;
            while (System.nanoTime() < deadline) {
                if (Files.exists(READY_FLAG)) {
                    try {
                        readyTick = Long.parseLong(Files.readString(READY_FLAG).trim());
                        if (readyTick > lastProcessedTick) {
                            foundReady = true;
                            break;
                        }
                    } catch (Exception e) {
                        // ignore and keep waiting
                    }
                }
            }
            
            if (!foundReady) {
                System.out.println("WARNING: Timed out waiting for bridge to write new data");
            }

            ResourceSet resourceSet = new ResourceSetImpl();
            resourceSet.getResourceFactoryRegistry()
                .getExtensionToFactoryMap()
                .put(Resource.Factory.Registry.DEFAULT_EXTENSION,
                     new XMIResourceFactoryImpl());

            Resource resource = loadResource(resourceSet);

            if (resource == null || resource.getContents().isEmpty()) {
                continue;
            }

            EMFScope scope = new EMFScope(resource);
            ViatraQueryEngine engine = ViatraQueryEngine.on(scope);

            BatchTransformationStatements statements =
                BatchTransformation.forEngine(engine)
                    .build()
                    .getTransformationStatements();

            System.out.println("--- Executing Batch Transformation ---");

            // Fire rules
            statements.fireAllCurrent(nearCollisionRule);
            statements.fireAllCurrent(superNearRule);
            statements.fireAllCurrent(veryNearRule);
            statements.fireAllCurrent(nearRule);
            statements.fireAllCurrent(visibleRule);
            statements.fireAllCurrent(removeRule);
            
            // Spatial direction rules
            statements.fireAllCurrent(frontRightRule);
            statements.fireAllCurrent(rightFrontRule);
            statements.fireAllCurrent(rightRearRule);
            statements.fireAllCurrent(rearRightRule);
            statements.fireAllCurrent(rearLeftRule);
            statements.fireAllCurrent(leftRearRule);
            statements.fireAllCurrent(leftFrontRule);
            statements.fireAllCurrent(frontLeftRule);

            statements.fireAllCurrent(vehicleOnLaneRule);
            statements.fireAllCurrent(rssLonRule);
            statements.fireAllCurrent(removeRssLonRule);
            statements.fireAllCurrent(rssLatRule);
            statements.fireAllCurrent(removeRssLatRule);
            statements.fireAllCurrent(removeVehicleOnLaneRule);

            saveResource(resource);

            // Signal that VIATRA has completed one round of evaluation
            Files.writeString(DONE_FLAG, Long.toString(readyTick));

            lastProcessedTick = readyTick;

            long end = System.nanoTime();
            System.out.println("VIATRA took: " + (end - start) / 1_000_000 + " ms");
        }
    }

    // Shared logic for all vehicle-distance rules
    private void applyDistance(Vehicle v1, Vehicle v2, String distance) {

        if (v1.getId().compareTo(v2.getId()) >= 0) return;

        Scene scene = (Scene) v1.eContainer();

        Edge edge = scene.getEdges().stream()
            .filter(e -> "vehicle".equals(e.getType()))
            .filter(e -> e.getSource() == v1 && e.getTarget() == v2)
            .findFirst()
            .orElse(null);

        if (edge == null) {
            edge = SceneGraphModelFactory.eINSTANCE.createEdge();
            edge.setSource(v1);
            edge.setTarget(v2);
            edge.setType("vehicle");
            edge.setSpatial("");
            scene.getEdges().add(edge);

            System.out.println("Created edge: " + v1.getId() + " -> " + v2.getId());
        }

        if (!distance.equals(edge.getDistance())) {
            edge.setDistance(distance);
            System.out.println("Updated distance: " + v1.getId() + " -> " + v2.getId() + " = " + distance);
        }
    }

    // Shared logic for spatial direction rules
    private void applySpatial(Vehicle source, Vehicle target, String spatial) {

        if (source.getId().compareTo(target.getId()) >= 0) return;

        Scene scene = (Scene) source.eContainer();

        Edge edge = scene.getEdges().stream()
            .filter(e -> "vehicle".equals(e.getType()))
            .filter(e -> e.getSource() == source && e.getTarget() == target)
            .findFirst()
            .orElse(null);

        if (edge != null) {
            if (!spatial.equals(edge.getSpatial())) {
                edge.setSpatial(spatial);
                System.out.println("Updated spatial: " + source.getId() + " -> " + target.getId() + " = " + spatial);
            }
        }
    }

    private void applyLane(Vehicle vehicle, RoadSegment lane) {

        Scene scene = (Scene) vehicle.eContainer();

        Edge edge = scene.getEdges().stream()
            .filter(e -> "lane".equals(e.getType()))
            .filter(e -> e.getSource() == vehicle && e.getTarget() == lane)
            .findFirst()
            .orElse(null);

        if (edge == null) {
            edge = SceneGraphModelFactory.eINSTANCE.createEdge();
            edge.setSource(vehicle);
            edge.setTarget(lane);
            edge.setType("lane");
            scene.getEdges().add(edge);
            System.out.println("Created lane edge: " + vehicle.getId() + " -> " + lane.getId());
        }
    }

    private void removeLane(Vehicle vehicle, RoadSegment lane) {

        Scene scene = (Scene) vehicle.eContainer();

        List<Edge> toRemove = scene.getEdges().stream()
            .filter(e -> "lane".equals(e.getType()))
            .filter(e -> e.getSource() == vehicle && e.getTarget() == lane)
            .collect(Collectors.toList());

        toRemove.forEach(e -> {
            scene.getEdges().remove(e);
            System.out.println("Removed lane edge: " + vehicle.getId() + " -> " + lane.getId());
        });
    }

    private void applyRssEdge(Vehicle ego, Vehicle other, String edgeType) {

        Scene scene = (Scene) ego.eContainer();

        Edge edge = scene.getEdges().stream()
            .filter(e -> edgeType.equals(e.getType()))
            .filter(e -> e.getSource() == ego && e.getTarget() == other)
            .findFirst()
            .orElse(null);

        if (edge == null) {
            edge = SceneGraphModelFactory.eINSTANCE.createEdge();
            edge.setSource(ego);
            edge.setTarget(other);
            edge.setType(edgeType);
            scene.getEdges().add(edge);
            System.out.println("[RSS] " + edgeType + ": " + ego.getId() + " -> " + other.getId());
        }
    }

    private void removeRssEdge(Vehicle ego, Vehicle other, String edgeType) {

        Scene scene = (Scene) ego.eContainer();

        List<Edge> toRemove = scene.getEdges().stream()
            .filter(e -> edgeType.equals(e.getType()))
            .filter(e -> e.getSource() == ego && e.getTarget() == other)
            .collect(Collectors.toList());

        toRemove.forEach(e -> {
            scene.getEdges().remove(e);
            System.out.println("[RSS] Removed " + edgeType + ": " + ego.getId() + " -> " + other.getId());
        });
    }

    private Resource loadResource(ResourceSet rs) {
        int maxAttempts = 40;

        for (int attempt = 0; attempt < maxAttempts; attempt++) {
            try {
                return rs.getResource(URI.createFileURI(MODEL_PATH), true);
            } catch (Exception e) {
                // ignore and retry
            }
        }
        return null;
    }

    private void saveResource(Resource resource) {
        int maxAttempts = 40;

        for (int attempt = 0; attempt < maxAttempts; attempt++) {
            try {
                // Persist only edges to preserve original node ordering and other attributes
                saveEdgesOnly(resource);
                System.out.println("Model edges updated and saved.");
                return;
            } catch (Exception e) {
                // ignore and retry
            }
        }

        System.err.println("ERROR: Failed to save resource.");
    }

    /**
     * Writes only the serialized <edges .../> elements back into the XMI file
     * at MODEL_PATH. This preserves the original node ordering and other
     * attributes while updating edges produced by VIATRA rules.
     */
    private void saveEdgesOnly(Resource resource) {
        try {
            if (resource.getContents().isEmpty()) return;

            Object root = resource.getContents().get(0);
            if (!(root instanceof scenegraph.Scene)) return;

            scenegraph.Scene scene = (scenegraph.Scene) root;

            // Build edges XML fragment
            StringBuilder edgesXml = new StringBuilder();
            for (scenegraph.Edge e : scene.getEdges()) {
                int srcIdx = scene.getNodes().indexOf(e.getSource());
                int tgtIdx = scene.getNodes().indexOf(e.getTarget());
                String type = e.getType() == null ? "" : escapeXml(e.getType());
                String distance = e.getDistance() == null ? "" : escapeXml(e.getDistance());
                String spatial = e.getSpatial() == null ? "" : escapeXml(e.getSpatial());

                edgesXml.append("  <edges ");
                edgesXml.append("type=\"").append(type).append("\" ");
                edgesXml.append("distance=\"").append(distance).append("\" ");
                edgesXml.append("spatial=\"").append(spatial).append("\" ");
                edgesXml.append("source=\"//@nodes.").append(srcIdx).append("\" ");
                edgesXml.append("target=\"//@nodes.").append(tgtIdx).append("\" />\n");
            }

            // Read existing file content
            String content = Files.readString(MODEL_FILE, StandardCharsets.UTF_8);

            // Find where edges start and replace until the closing scene tag
            int firstEdges = content.indexOf("\n  <edges");
            int closeTag = content.lastIndexOf("</scenegraph:Scene>");

            String newContent;
            if (firstEdges != -1 && closeTag != -1) {
                newContent = content.substring(0, firstEdges + 1) + edgesXml.toString() + content.substring(closeTag);
            } else if (closeTag != -1) {
                // No edges previously present: insert before closing tag
                String prefix = content.substring(0, closeTag);
                newContent = prefix + "\n" + edgesXml.toString() + content.substring(closeTag);
            } else {
                // Fallback: overwrite entire content
                newContent = content + "\n" + edgesXml.toString();
            }

            Files.writeString(MODEL_FILE, newContent, StandardCharsets.UTF_8);

        } catch (Exception ex) {
            throw new RuntimeException("Failed to write edges-only XMI", ex);
        }
    }

    private String escapeXml(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;").replace("'", "&apos;");
    }

    @Override
    public void stop() {}
}
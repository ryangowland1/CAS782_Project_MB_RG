// NOTE: At some point should move to event-based transforms. This may require setting up a socket interface so the Python
// scene graph output can send notifications of model changes to VIATRA

package apiqueries;

import java.io.File;
import java.io.IOException;

import java.util.Collections;
import java.util.List;

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
import scenegraph.SceneGraphModelFactory;

// VIATRA Query Import
import queries.VisibleDistance;
import queries.RemoveEdge;

public class QueryRunner implements IApplication {

    private static final String MODEL_PATH = 
        "C:\\Users\\marko\\Documents\\CAS782_Project_MB_RG\\data\\stream\\latest_snapshot.xmi";
    private static final long POLL_INTERVAL_MS = 200;

    @Override
    public Object start(IApplicationContext context) throws Exception {
        while (true) {
            long start = System.nanoTime();
            Resource resource = loadResource();
            
            if (resource == null || resource.getContents().isEmpty()) {
                System.err.println("ERROR: Resource failed to load or is empty.");
                continue; // skip this iteration
            }
            
            EMFScope scope = new EMFScope(resource);
            ViatraQueryEngine engine = ViatraQueryEngine.on(scope);

            // 1. Define the Rule
            BatchTransformationRule<VisibleDistance.Match, VisibleDistance.Matcher> proximityRule = 
        	    new BatchTransformationRuleFactory().createRule(VisibleDistance.instance())
        	    .name("VisibleDistanceRule")
        	    .action(match -> {
        	        Vehicle v1 = match.getO1();
        	        Vehicle v2 = match.getO2();

        	        // Only proceed if source ID < target ID
        	        if (v1.getId().compareTo(v2.getId()) >= 0) {
        	            return; // Skip this pair
        	        }

        	        Scene scene = (Scene) v1.eContainer();

        	        // Check if an edge already exists (and get it)
        	        Edge existingEdge = scene.getEdges().stream()
        	            .filter(e -> "proximity".equals(e.getType()))
        	            .filter(e -> e.getSource() == v1 && e.getTarget() == v2)
        	            .findFirst()
        	            .orElse(null);

                    if (existingEdge == null) {
        	            // No edge exists → create one
        	            Edge edge = SceneGraphModelFactory.eINSTANCE.createEdge();
        	            edge.setDistance("Visible");
        	            edge.setSource(v1);
        	            edge.setTarget(v2);
        	            edge.setType("proximity");
        	            scene.getEdges().add(edge);
        	            System.out.println("Created visible distance edge: " +
        	                               v1.getId() + " -> " + v2.getId() + " with distance Visible");
        	        } else {
        	            // Edge exists → update distance if needed
        	            if (!"Visible".equals(existingEdge.getDistance())) {
        	                existingEdge.setDistance("Visible");
        	                System.out.println("Updated distance for edge: " +
        	                                   v1.getId() + " -> " + v2.getId() + " to Visible");
        	            }
        	        }
        	    })
        	    .build();
            
            BatchTransformationRule<RemoveEdge.Match, RemoveEdge.Matcher> removeProximityRule =
        	    new BatchTransformationRuleFactory().createRule(RemoveEdge.instance())
        	    .name("RemoveEdgeRule")
        	    .action(match -> {
        	        Vehicle v1 = match.getO1();
        	        Vehicle v2 = match.getO2();
        	        Scene scene = (Scene) v1.eContainer();

        	        // Find the edge connecting these two vehicles (if it exists)
        	        List<Edge> toRemove = scene.getEdges().stream()
        	            .filter(e -> "proximity".equals(e.getType()))
        	            .filter(e -> (e.getSource() == v1 && e.getTarget() == v2) ||
        	                         (e.getSource() == v2 && e.getTarget() == v1))
        	            .toList(); // Java 16+ toList()

        	        // Remove any edges between far vehicles
        	        toRemove.forEach(e -> {
        	            scene.getEdges().remove(e);
        	            System.out.println("Removed edge (vehicles are too far): " +
        	                               e.getSource().getId() + " <-> " + e.getTarget().getId());
        	        });
        	    })
        	    .build();
            
            // 2. Initialize and Fire the Transformation
            BatchTransformation transformation = BatchTransformation.forEngine(engine).build();
            BatchTransformationStatements statements = transformation.getTransformationStatements();
            
            System.out.println("--- Executing Batch Transformation ---");
            statements.fireAllCurrent(proximityRule);
            statements.fireAllCurrent(removeProximityRule);

            saveResource(resource);
            long end = System.nanoTime();
            System.out.println("VIATRA took: " + (end - start) / 1_000_000 + " ms");

            // Sleep POLL_INTERVAL_MS milliseconds before reloading
            Thread.sleep(POLL_INTERVAL_MS);
        }
    }

    private Resource loadResource() {
    	File modelFile = new File(MODEL_PATH);
    	int maxAttempts = 40;

    	for (int attempt = 0; attempt < maxAttempts; attempt++) {
    	    try {
    	        ResourceSet rs = new ResourceSetImpl();
    	        rs.getResourceFactoryRegistry()
    	          .getExtensionToFactoryMap()
    	          .put(Resource.Factory.Registry.DEFAULT_EXTENSION,
    	               new XMIResourceFactoryImpl());

    	        Resource res = rs.getResource(
    	                URI.createFileURI(MODEL_PATH), true);

    	        return res; // success

    	    } catch (Exception e) {
    	        // EMF may wrap IOExceptions inside WrappedException
    	        Throwable cause = e.getCause();

    	        boolean isIOIssue =
    	                e instanceof IOException ||
    	                cause instanceof IOException;

    	        if (!isIOIssue) {
    	            // Not an IO-related issue → don't retry
    	            e.printStackTrace();
    	            return null;
    	        }

    	        // Otherwise retry
    	    }

    	    // Retry delay
    	    try {
    	        Thread.sleep(20);
    	    } catch (InterruptedException ie) {
    	        Thread.currentThread().interrupt();
    	        return null;
    	    }
    	}

    	// Failed after retries
    	return null;
    }
    
    // TODO: Implement retry logic here like with loadResource()
    private void saveResource(Resource resource) {
        try {
            resource.save(Collections.emptyMap());
            System.out.println("Model updated and saved.");
        } catch (IOException e) { }
    }

    @Override
    public void stop() {}
}
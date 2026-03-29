package apiqueries;

import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;

// EMF imports
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;

// VIATRA imports
import org.eclipse.viatra.query.runtime.api.ViatraQueryEngine;
import org.eclipse.viatra.query.runtime.emf.EMFScope;

// Your generated query
import queries.SlowVehicle;

public class QueryRunner implements IApplication {

    private static final String MODEL_PATH = 
        "C:\\Users\\marko\\Documents\\CAS782_Project_MB_RG\\data\\stream\\latest_snapshot.xmi";
    private static final long POLL_INTERVAL_MS = 2000;

    @Override
    public Object start(IApplicationContext context) throws Exception {

        while (true) { // infinite loop to reload every 2 seconds
            EMFScope scope = initializeModelScope();
            ViatraQueryEngine engine = prepareQueryEngine(scope);

            long start = System.nanoTime();
            printAllMatches(engine);
            long end = System.nanoTime();
            System.out.println("VIATRA took: " + (end - start) / 1_000_000 + " ms");

            // Sleep 2 seconds before reloading
            Thread.sleep(POLL_INTERVAL_MS);
        }
    }

    @Override
    public void stop() {
        // Headless applications do not require specific stop steps
    }

    private EMFScope initializeModelScope() {
        ResourceSet rs = new ResourceSetImpl();
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
            .put(Resource.Factory.Registry.DEFAULT_EXTENSION, new XMIResourceFactoryImpl());

        // Load resource and force reload to pick up any changes
        Resource resource = rs.getResource(URI.createFileURI(MODEL_PATH), true);
        try {
            resource.unload();  // clear cached content
            resource.load(null); // reload from file
        } catch (Exception e) {
            e.printStackTrace();
        }

        return new EMFScope(rs);
    }

    private ViatraQueryEngine prepareQueryEngine(EMFScope scope) {
        // Access managed query engine
        return ViatraQueryEngine.on(scope);
    }

    private void printAllMatches(ViatraQueryEngine engine) {
        // Access pattern matcher
        SlowVehicle.Matcher matcher = SlowVehicle.Matcher.on(engine);

        // Get and iterate over all matches
        for (SlowVehicle.Match match : matcher.getAllMatches()) {
            System.out.println("Match found: " + match);
        }
    }
}
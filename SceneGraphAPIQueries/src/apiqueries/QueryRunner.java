package apiqueries;

import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;

//EMF imports
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;

//VIATRA imports
import org.eclipse.viatra.query.runtime.api.ViatraQueryEngine;
import org.eclipse.viatra.query.runtime.emf.EMFScope;

//Your generated query (this depends on your project!)
import queries.SlowVehicle;
public class QueryRunner implements IApplication {

	@Override
	public Object start(IApplicationContext context) throws Exception {
		
		EMFScope scope = initializeModelScope();
	    ViatraQueryEngine engine = prepareQueryEngine(scope);
	    
	    long start = System.nanoTime();
		printAllMatches(engine);
		long end = System.nanoTime();
		System.out.println("VIATRA took: " + (end-start)/1000000 + " ms");
		
        // Return value 0 is considered as a successful execution on Unix systems
		return 0;
	}

	@Override
	public void stop() {
        // Headless applications do not require specific stop steps
	}
	
	private EMFScope initializeModelScope() {
		ResourceSet rs = new ResourceSetImpl();
		rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
	    	.put(Resource.Factory.Registry.DEFAULT_EXTENSION, new XMIResourceFactoryImpl());
		
		rs.getResource(
			    URI.createFileURI(
			    	"C:/Users/marko/Documents/CAS782_Project_MB_RG/SceneGraphModel/demo_mock.xmi"
			    ),
			true
		);

		return new EMFScope(rs);
	}
	
	private ViatraQueryEngine prepareQueryEngine(EMFScope scope) {
		// Access managed query engine
	    ViatraQueryEngine engine = ViatraQueryEngine.on(scope);

		return engine;
	}
	
	private void printAllMatches(ViatraQueryEngine engine) {
		// Access pattern matcher
		SlowVehicle.Matcher matcher = SlowVehicle.Matcher.on(engine);
		// Get and iterate over all matches
		for (SlowVehicle.Match match : matcher.getAllMatches()) {
			// Print all the matches to the standard output
			System.out.println("Hi");
		}
	}
}

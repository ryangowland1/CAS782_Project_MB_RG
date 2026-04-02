package queries;

public class scenegraphhelper {

    /**
     * Calculate the relative angle from source to target node.
     *
     * @param sourceX x coordinate of source node
     * @param sourceY y coordinate of source node
     * @param sourceHeading heading (in radians) of source node
     * @param targetX x coordinate of target node
     * @param targetY y coordinate of target node
     * @return angle in radians relative to source's heading
     *         angle > 0 = target is to the left
     *         angle < 0 = target is to the right
     */
    public static double calculateAngle(double sourceX, double sourceY, double sourceHeading,
                                       double targetX, double targetY) {
        double dx = targetX - sourceX;
        double dy = targetY - sourceY;
        double angleToTarget = Math.atan2(dy, dx);
        double relativeAngle = angleToTarget - sourceHeading;

        // Normalize to [-π, π]
        while (relativeAngle > Math.PI) {
            relativeAngle -= 2 * Math.PI;
        }
        while (relativeAngle < -Math.PI) {
            relativeAngle += 2 * Math.PI;
        }

        return relativeAngle;
    }

    public static boolean isVehicleInLane(double vehicleX, double vehicleY,
                                          double laneX, double laneY,
                                          double laneHeading, double laneLength,
                                          double laneWidth) {
        double dx = vehicleX - laneX;
        double dy = vehicleY - laneY;

        double cos = Math.cos(-laneHeading);
        double sin = Math.sin(-laneHeading);

        double longitudinal = dx * cos - dy * sin;
        double lateral = dx * sin + dy * cos;

        return Math.abs(longitudinal) <= laneLength / 2.0
            && Math.abs(lateral) <= laneWidth / 2.0;
    }
}
